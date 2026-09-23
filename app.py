"""
Campus Hostel Companion - Flask Application Entry Point
"""

import os
import uuid
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from dotenv import load_dotenv

# Load environment variables from .env file (if present)
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
application = app

# -------------------------------------------------------------------------
# Flask secret key — required for session management
# -------------------------------------------------------------------------
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-fallback-secret-key")

# -------------------------------------------------------------------------
# Services
# -------------------------------------------------------------------------
from services.cognito import register_user, authenticate_user, confirm_user, resend_verification_code
from services.dynamodb import (
    get_todays_menu,
    get_weekly_menu,
    save_weekly_menu,
    create_complaint,
    get_user_complaints,
    get_organization_complaints,
    get_complaint_by_id,
    update_complaint_status,
    create_organization,
    get_organization,
    get_organization_by_invite_code,
    add_organization_member,
    get_user_membership,
    get_organization_members,
    get_announcements,
    DAYS_OF_WEEK,
)
from services.whatsapp import send_warden_complaint_notification
from services.ai_service import analyze_complaint


# -------------------------------------------------------------------------
# Helper: Authentication & Authorization Decorators
# -------------------------------------------------------------------------
def is_logged_in() -> bool:
    """Returns True if a valid user session exists."""
    return "user" in session and bool(session["user"].get("username"))


def login_required(f):
    """Decorator to protect routes that require authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_logged_in():
            flash("Please log in to continue.", "info")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


def warden_required(f):
    """Decorator to restrict routes to authorized wardens/guardians only."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_logged_in():
            flash("Please log in to continue.", "info")
            return redirect(url_for("login"))
        user = session.get("user", {})
        role = user.get("role", "student")
        if role != "warden":
            flash("Access denied: Warden authorization required.", "error")
            return redirect(url_for("dashboard")), 403
        return f(*args, **kwargs)
    return decorated


def sync_user_organization_session(username: str):
    """Helper to fetch and synchronize organization & role into session."""
    if not username:
        return
    try:
        membership = get_user_membership(username)
        if membership:
            org_id = membership.get("organization_id", "")
            role = membership.get("role", "student")
            org = get_organization(org_id) if org_id else None
            org_name = org.get("organization_name", "Campus Hostel") if org else "Campus Hostel"

            session["organization_id"] = org_id
            session["organization_name"] = org_name
            if "user" in session:
                session["user"]["role"] = role
                session["user"]["organization_id"] = org_id
                session["user"]["organization_name"] = org_name
    except Exception:
        pass


# =========================================================================
# PUBLIC ROUTES
# =========================================================================

@app.route("/")
def index():
    """Landing page — accessible without login."""
    if is_logged_in():
        user = session.get("user", {})
        if user.get("role") == "warden":
            return redirect(url_for("warden_dashboard"))
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/health")
def health():
    """Health-check endpoint for load balancers and deployment verification."""
    return jsonify({"status": "ok"})


# =========================================================================
# AUTHENTICATION ROUTES (AWS Cognito)
# =========================================================================

@app.route("/auth", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    """Handle user login/registration via AWS Cognito or display the auth card."""
    if is_logged_in():
        user = session.get("user", {})
        if user.get("role") == "warden":
            return redirect(url_for("warden_dashboard"))
        return redirect(url_for("dashboard"))

    # Preserve active tab (login or register) for template
    active_tab = request.args.get("tab", "login")

    if request.method == "POST":
        form_tab = request.form.get("tab", "login")

        if form_tab == "register":
            # ── Registration branch ──────────────────────────────────────────
            display_name = request.form.get("username", "").strip()
            email        = request.form.get("reg_email", "").strip()
            password     = request.form.get("reg_password", "").strip()

            if not email or not password:
                flash("Email and password are required to register.", "error")
                return render_template("auth.html", active_tab="register")

            if len(password) < 8:
                flash("Password must be at least 8 characters.", "error")
                return render_template("auth.html", active_tab="register")

            result = register_user(display_name or email.split("@")[0], email, password)
            if result["success"]:
                if result.get("user_confirmed"):
                    flash("Account created! You can sign in now.", "success")
                    return render_template("auth.html", active_tab="login")
                else:
                    # Redirect to email verification page
                    session["pending_verification_email"] = email
                    return redirect(url_for("verify_email"))
            else:
                flash(result["error"], "error")
                return render_template("auth.html", active_tab="register")

        else:
            # ── Login branch ─────────────────────────────────────────────────
            username = request.form.get("email", "").strip() or request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

            if not username or not password:
                flash("Email and password are both required.", "error")
                return render_template("auth.html", active_tab="login")

            result = authenticate_user(username, password)
            if result["success"]:
                # Store only minimal user identity in session — avoid large tokens or payloads
                raw_user = result.get("user", {})
                user_data = {
                    "username": raw_user.get("username") or username.strip().split("@")[0],
                    "email": raw_user.get("email") or (username.strip() if "@" in username else ""),
                }
                if raw_user.get("sub"):
                    user_data["sub"] = raw_user["sub"]
                if raw_user.get("user_id"):
                    user_data["user_id"] = raw_user["user_id"]
                if raw_user.get("role"):
                    user_data["role"] = raw_user["role"]

                session["user"] = user_data
                display = user_data.get("username") or username

                # Synchronize membership & organization
                sync_user_organization_session(display)

                user_role = session.get("user", {}).get("role", "student")
                flash(f"Welcome back, {display}!", "success")

                # If no organization is joined yet, prompt onboarding
                if not session.get("organization_id"):
                    return redirect(url_for("onboarding"))

                if user_role == "warden":
                    return redirect(url_for("warden_dashboard"))
                return redirect(url_for("dashboard"))
            else:
                if result.get("not_confirmed"):
                    target_email = result.get("email") or username
                    session["pending_verification_email"] = target_email
                    flash("Your email is not verified yet. Please enter the verification code sent to your email.", "warning")
                    return redirect(url_for("verify_email", email=target_email))
                flash(result["error"], "error")
                return render_template("auth.html", active_tab="login")

    return render_template("auth.html", active_tab=active_tab)


@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    """Verify email with Cognito confirmation code sent after registration."""
    if is_logged_in():
        return redirect(url_for("dashboard"))

    email = session.get("pending_verification_email", "")
    # Allow ?email= param for direct linking
    if not email:
        email = request.args.get("email", "").strip()

    if request.method == "POST":
        action = request.form.get("action", "verify")
        posted_email = request.form.get("email", "").strip()
        if posted_email:
            email = posted_email

        if not email:
            flash("Please enter your college email address.", "error")
            return render_template("verify_email.html", email="")

        if action == "resend":
            result = resend_verification_code(email)
            if result["success"]:
                flash("A new verification code has been sent to your email.", "success")
            else:
                flash(result["error"], "error")
            return render_template("verify_email.html", email=email)

        # Default: verify the code
        code = request.form.get("code", "").strip()
        if not code:
            flash("Please enter the verification code.", "error")
            return render_template("verify_email.html", email=email)

        result = confirm_user(email, code)
        if result["success"]:
            session.pop("pending_verification_email", None)
            flash("Email verified successfully! You can now sign in.", "success")
            return redirect(url_for("login"))
        else:
            flash(result["error"], "error")
            return render_template("verify_email.html", email=email)

    return render_template("verify_email.html", email=email)


@app.route("/guest-login")
def guest_login():
    """Log in as a guest resident."""
    session["user"] = {
        "username": "guest",
        "email": "guest@campus.edu",
        "role": "student",
    }
    session["organization_id"] = "org_campus_default"
    session["organization_name"] = "Campus Hostel"
    flash("Signed in as guest.", "info")
    return redirect(url_for("dashboard"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """Handle new student registration via AWS Cognito — redirects to /auth."""
    return redirect(url_for("login", tab="register"))


@app.route("/logout")
def logout():
    """Clear session and redirect to landing page."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# =========================================================================
# ONBOARDING & ORGANIZATION MANAGEMENT
# =========================================================================

@app.route("/onboarding", methods=["GET"])
@login_required
def onboarding():
    """One-time setup/join screen for organizations/hostels."""
    user = session.get("user", {})
    return render_template("onboarding.html", user=user)


@app.route("/join-organization", methods=["POST"])
@login_required
def join_organization():
    """Join an existing organization securely using an invite/join code."""
    invite_code = request.form.get("invite_code", "").strip().upper()
    user = session.get("user", {})
    user_id = user.get("username", "")

    if not invite_code:
        flash("Please enter an organization invite code.", "error")
        return redirect(url_for("onboarding"))

    org = get_organization_by_invite_code(invite_code)
    if not org:
        flash("Invalid invite code. Please check with your hostel warden.", "error")
        return redirect(url_for("onboarding"))

    org_id = org.get("organization_id")
    org_name = org.get("organization_name", "Hostel")

    # Add student membership
    success, err = add_organization_member(
        organization_id=org_id,
        user_id=user_id,
        role="student",
        user_name=user.get("username", user_id),
    )

    if success:
        session["organization_id"] = org_id
        session["organization_name"] = org_name
        if "user" in session:
            session["user"]["role"] = "student"
            session["user"]["organization_id"] = org_id
            session["user"]["organization_name"] = org_name
        flash(f"Successfully joined {org_name}!", "success")
        return redirect(url_for("dashboard"))
    else:
        flash(f"Could not join organization: {err}", "error")
        return redirect(url_for("onboarding"))


@app.route("/create-organization", methods=["POST"])
@login_required
def create_organization_route():
    """Allow a warden/guardian to create and register an organization."""
    org_name = request.form.get("organization_name", "").strip()
    org_type = request.form.get("organization_type", "College Hostel").strip()
    member_count = request.form.get("member_count", "100").strip()
    warden_phone = request.form.get("warden_phone", "").strip()
    warden_name = request.form.get("warden_name", "").strip()

    user = session.get("user", {})
    user_id = user.get("username", "")

    if not org_name:
        flash("Organization/Hostel name is required.", "error")
        return redirect(url_for("onboarding"))

    if not warden_phone:
        flash("Warden contact phone number is required for notification setup.", "error")
        return redirect(url_for("onboarding"))

    # Create organization in DynamoDB
    org, err = create_organization(
        name=org_name,
        org_type=org_type,
        member_count=member_count,
        creator_id=user_id,
        phone=warden_phone,
    )

    if not org:
        flash(f"Failed to create organization: {err}", "error")
        return redirect(url_for("onboarding"))

    org_id = org["organization_id"]
    invite_code = org["invite_code"]

    # Assign warden role to creator
    add_organization_member(
        organization_id=org_id,
        user_id=user_id,
        role="warden",
        user_name=warden_name or user_id,
    )

    session["organization_id"] = org_id
    session["organization_name"] = org_name
    if "user" in session:
        session["user"]["role"] = "warden"
        session["user"]["organization_id"] = org_id
        session["user"]["organization_name"] = org_name

    flash(
        f"Organization created successfully! Your Hostel Invite Code is {invite_code}. Share this code with students.",
        "success",
    )
    return redirect(url_for("warden_dashboard"))


# =========================================================================
# WARDEN DASHBOARD & MANAGEMENT (Protected: Warden Role Required)
# =========================================================================

@app.route("/warden/complaints")
@app.route("/warden/dashboard")
@login_required
@warden_required
def warden_dashboard():
    """Warden Dashboard: View all complaints for the warden's organization."""
    user = session.get("user", {})
    user_id = user.get("username", "")

    sync_user_organization_session(user_id)
    org_id = session.get("organization_id", "")
    org = get_organization(org_id) if org_id else {}

    complaints_list = get_organization_complaints(org_id) if org_id else []

    submitted_count = sum(1 for c in complaints_list if str(c.get("status", "")).lower() in ["submitted", "pending", "open"])
    in_progress_count = sum(1 for c in complaints_list if str(c.get("status", "")).lower() in ["in progress", "under review"])
    resolved_count = sum(1 for c in complaints_list if str(c.get("status", "")).lower() == "resolved")
    total_count = len(complaints_list)

    return render_template(
        "warden_dashboard.html",
        user=user,
        organization=org,
        complaints=complaints_list,
        submitted_count=submitted_count,
        in_progress_count=in_progress_count,
        resolved_count=resolved_count,
        total_count=total_count,
    )


@app.route("/warden/complaints/<complaint_id>/status", methods=["POST"])
@login_required
@warden_required
def update_complaint_status_route(complaint_id: str):
    """Update complaint status by authorized warden."""
    new_status = request.form.get("status", "").strip()
    org_id = session.get("organization_id", "")

    valid_statuses = ["Submitted", "Under Review", "In Progress", "Resolved", "Rejected", "Pending"]
    if new_status not in valid_statuses:
        flash("Invalid status specified.", "error")
        return redirect(url_for("warden_dashboard"))

    success, err = update_complaint_status(complaint_id, new_status, organization_id=org_id)
    if success:
        flash(f"Complaint status updated to {new_status}.", "success")
    else:
        flash(f"Could not update status: {err}", "error")

    return redirect(url_for("warden_dashboard"))


# =========================================================================
# PROTECTED APPLICATION ROUTES (require login)
# =========================================================================

@app.route("/dashboard")
@login_required
def dashboard():
    """Show today's mess menu from DynamoDB, quick links, and complaints stats."""
    user = session.get("user", {})
    user_id = user.get("username", "")

    # Synchronize org data if available
    sync_user_organization_session(user_id)
    org_id = session.get("organization_id", "")

    menu = get_todays_menu()
    now_str = datetime.now().strftime("%A, %d %B %Y")
    user_complaints = get_user_complaints(user_id, org_id) if user_id else []
    pending_count = sum(1 for c in user_complaints if str(c.get("status", "")).lower() in ["pending", "open", "in progress", "submitted", "under review"])
    resolved_count = sum(1 for c in user_complaints if str(c.get("status", "")).lower() == "resolved")
    total_count = len(user_complaints)

    return render_template(
        "dashboard.html",
        menu=menu,
        user=user,
        now=now_str,
        complaints=user_complaints,
        pending_count=pending_count,
        resolved_count=resolved_count,
        total_count=total_count,
    )


@app.route("/weekly-menu")
@login_required
def weekly_menu():
    """Show the full 7-day mess menu."""
    user = session.get("user", {})
    weekly = get_weekly_menu()
    today = datetime.now().strftime("%A")
    return render_template("weekly_menu.html", weekly=weekly, days=DAYS_OF_WEEK, today=today, user=user)


@app.route("/edit-menu", methods=["GET", "POST"])
@login_required
def edit_menu():
    """Allow authenticated hostel users to update the weekly mess menu."""
    user = session.get("user", {})

    if request.method == "POST":
        menu_data = {}
        for day in DAYS_OF_WEEK:
            menu_data[day] = {
                "breakfast": request.form.get(f"{day}_breakfast", "").strip(),
                "lunch":     request.form.get(f"{day}_lunch", "").strip(),
                "dinner":    request.form.get(f"{day}_dinner", "").strip(),
            }

        # Validate at least one meal is filled per day
        errors = []
        for day in DAYS_OF_WEEK:
            entry = menu_data[day]
            if not entry["breakfast"] or not entry["lunch"] or not entry["dinner"]:
                errors.append(f"{day}: all three meals (Breakfast, Lunch, Dinner) are required.")

        if errors:
            flash(" | ".join(errors), "error")
            weekly = get_weekly_menu()
            return render_template("edit_menu.html", weekly=weekly, days=DAYS_OF_WEEK, user=user)

        success, err = save_weekly_menu(menu_data)
        if success:
            flash("Weekly menu updated successfully!", "success")
            return redirect(url_for("weekly_menu"))
        else:
            flash(f"Failed to save menu: {err}", "error")
            weekly = get_weekly_menu()
            return render_template("edit_menu.html", weekly=weekly, days=DAYS_OF_WEEK, user=user)

    weekly = get_weekly_menu()
    return render_template("edit_menu.html", weekly=weekly, days=DAYS_OF_WEEK, user=user)


@app.route("/complaints")
@login_required
def complaints():
    """Show the logged-in user's own complaint history strictly isolated from others."""
    user = session.get("user", {})
    user_id = user.get("username", "")
    org_id = session.get("organization_id", "")
    user_complaints = get_user_complaints(user_id, org_id)
    return render_template("complaints.html", complaints=user_complaints, user=user)


@app.route("/complaints/<complaint_id>")
@login_required
def view_single_complaint(complaint_id: str):
    """
    Direct single complaint access.
    Enforces strict authorization: Accessible ONLY by the student who created it
    or by an authorized Warden of the same organization.
    """
    user = session.get("user", {})
    user_id = user.get("username", "")
    role = user.get("role", "student")
    user_org_id = session.get("organization_id", "")

    complaint = get_complaint_by_id(complaint_id)
    if not complaint:
        flash("Complaint not found.", "error")
        return redirect(url_for("complaints")), 404

    is_owner = (complaint.get("user_id") == user_id)
    is_authorized_warden = (role == "warden" and complaint.get("organization_id") == user_org_id)

    if not (is_owner or is_authorized_warden):
        flash("Unauthorized access: You do not have permission to view this complaint.", "error")
        return redirect(url_for("complaints")), 403

    return render_template("complaints.html", complaints=[complaint], user=user, single_view=True)


@app.route("/complaints/new", methods=["GET", "POST"])
@app.route("/raise-complaint", methods=["GET", "POST"])
@login_required
def raise_complaint():
    """Submit a new complaint with AI intelligence classification and warden notification."""
    user = session.get("user", {})

    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        category    = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()

        if not title or not category or not description:
            flash("All fields are required.", "error")
            return render_template("raise_complaint.html", user=user)

        user_id = user.get("username", "")
        org_id = session.get("organization_id", "org_campus_default")
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # 1. AI complaint intelligence layer (advisory, resilient)
        ai_data = analyze_complaint(title, description, category)
        priority = ai_data.get("priority", "Medium")

        new_complaint = {
            "complaint_id": str(uuid.uuid4()),
            "organization_id": org_id,
            "user_id": user_id,
            "title": title,
            "category": category,
            "description": description,
            "status": "Submitted",
            "priority": priority,
            "ai_classification": ai_data,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        # 2. Save complaint to DynamoDB
        success, err = create_complaint(new_complaint)
        if success:
            # 3. WhatsApp notification to warden (safe, silent fallback if disabled)
            org = get_organization(org_id) if org_id else {}
            warden_phone = org.get("warden_phone") if org else None
            send_warden_complaint_notification(new_complaint, recipient_phone=warden_phone)

            flash("Complaint submitted successfully.", "success")
            return redirect(url_for("complaints"))
        else:
            flash(f"Failed to submit complaint: {err}", "error")
            return render_template("raise_complaint.html", user=user)

    return render_template("raise_complaint.html", user=user)


@app.route("/announcements")
@login_required
def announcements():
    """Display hostel-wide announcements from AWS DynamoDB."""
    user = session.get("user", {})
    org_id = session.get("organization_id", "")
    all_announcements = get_announcements(organization_id=org_id)
    return render_template("announcements.html", announcements=all_announcements, user=user)


# =========================================================================
# Main Run
# =========================================================================
if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "True").lower() == "true"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)
