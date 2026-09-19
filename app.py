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

# -------------------------------------------------------------------------
# Flask secret key — required for session management
# -------------------------------------------------------------------------
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-fallback-secret-key")

# -------------------------------------------------------------------------
# Services
# -------------------------------------------------------------------------
from services.cognito import register_user, authenticate_user
from services.dynamodb import (
    get_todays_menu,
    create_complaint,
    get_user_complaints,
    get_announcements,
)


# -------------------------------------------------------------------------
# Helper: Authentication & Authorization
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


# =========================================================================
# PUBLIC ROUTES
# =========================================================================

@app.route("/")
def index():
    """Landing page — accessible without login."""
    if is_logged_in():
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
                else:
                    flash(
                        "Account created! Please check your email for a verification code, then sign in.",
                        "success",
                    )
                return render_template("auth.html", active_tab="login")
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
                session["user"] = result["user"]
                display = result["user"].get("username") or username
                flash(f"Welcome back, {display}!", "success")
                return redirect(url_for("dashboard"))
            else:
                flash(result["error"], "error")
                return render_template("auth.html", active_tab="login")

    return render_template("auth.html", active_tab=active_tab)


@app.route("/guest-login")
def guest_login():
    """Log in as a guest resident."""
    session["user"] = {"username": "guest", "email": "guest@campus.edu"}
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
# PROTECTED APPLICATION ROUTES (require login)
# =========================================================================

@app.route("/dashboard")
@login_required
def dashboard():
    """Show today's mess menu from DynamoDB, quick links, and complaints stats."""
    user = session.get("user", {})
    user_id = user.get("username", "")
    menu = get_todays_menu()
    now_str = datetime.now().strftime("%A, %d %B %Y")
    user_complaints = get_user_complaints(user_id) if user_id else []
    pending_count = sum(1 for c in user_complaints if str(c.get("status", "")).lower() in ["pending", "open", "in progress"])
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



@app.route("/complaints")
@login_required
def complaints():
    """Show the logged-in user's own complaint history strictly isolated from others."""
    user = session.get("user", {})
    user_id = user.get("username", "")
    user_complaints = get_user_complaints(user_id)
    return render_template("complaints.html", complaints=user_complaints, user=user)


@app.route("/complaints/new", methods=["GET", "POST"])
@app.route("/raise-complaint", methods=["GET", "POST"])
@login_required
def raise_complaint():
    """Submit a new complaint to AWS DynamoDB."""
    user = session.get("user", {})

    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        category    = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()

        if not title or not category or not description:
            flash("All fields are required.", "error")
            return render_template("raise_complaint.html", user=user)

        user_id = user.get("username", "")
        new_complaint = {
            "complaint_id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": title,
            "category": category,
            "description": description,
            "status": "Pending",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }

        success, err = create_complaint(new_complaint)
        if success:
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
    all_announcements = get_announcements()
    return render_template("announcements.html", announcements=all_announcements, user=user)


# =========================================================================
# Main Run
# =========================================================================
if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "True").lower() == "true"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)
