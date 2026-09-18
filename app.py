"""
Campus Hostel Companion - Flask Application Entry Point
"""

import os
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
# Helper: Check if the user is logged in
# -------------------------------------------------------------------------
def is_logged_in():
    """Returns True if a valid session exists for the current user."""
    # TODO (Cognito): Replace this check with token verification.
    #   After Cognito login, store the user's ID token and username in session:
    #       session["user"] = {"username": ..., "email": ..., "id_token": ...}
    #   Then validate the token here using the cognito service.
    return "user" in session


def login_required(f):
    """Decorator to protect routes that require authentication."""
    from functools import wraps
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
    """Health-check endpoint for load balancers / CI pipelines."""
    return jsonify({"status": "ok"})


# =========================================================================
# AUTH ROUTES
# =========================================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Handle user login.

    TODO (Cognito): Replace the stub below with real Cognito authentication.
      1. Import the cognito service:
             from services.cognito import authenticate_user
      2. Call it with the submitted username and password.
      3. On success, store the returned tokens and user info in session.
      4. Redirect to dashboard.
      5. On failure, flash an error message.

    Example:
        result = authenticate_user(username, password)
        if result["success"]:
            session["user"] = result["user"]
            return redirect(url_for("dashboard"))
        else:
            flash(result["error"], "error")
    """
    if is_logged_in():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Username and password are required.", "error")
            return render_template("index.html", show_login=True)

        # -----------------------------------------------------------
        # TODO (Cognito): Authenticate user via Cognito here.
        #   Remove the stub session below once Cognito is integrated.
        # -----------------------------------------------------------
        flash("Authentication is not yet connected. Please configure AWS Cognito.", "warning")
        return render_template("index.html", show_login=True)

    return render_template("index.html", show_login=True)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """
    Handle new user registration.

    TODO (Cognito): Replace the stub below with real Cognito sign-up.
      1. Import: from services.cognito import register_user
      2. Call: result = register_user(username, email, password)
      3. On success, redirect to a "confirm your email" page or login.
      4. On failure, flash the error returned by Cognito.
    """
    if is_logged_in():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username  = request.form.get("username", "").strip()
        email     = request.form.get("email", "").strip()
        password  = request.form.get("password", "").strip()

        if not username or not email or not password:
            flash("All fields are required.", "error")
            return render_template("index.html", show_signup=True)

        # -----------------------------------------------------------
        # TODO (Cognito): Register user via Cognito here.
        # -----------------------------------------------------------
        flash("Sign-up is not yet connected. Please configure AWS Cognito.", "warning")
        return render_template("index.html", show_signup=True)

    return render_template("index.html", show_signup=True)


@app.route("/logout")
def logout():
    """Clear the user session and redirect to the landing page."""
    # TODO (Cognito): Also revoke the Cognito refresh token if stored.
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# =========================================================================
# PROTECTED ROUTES (require login)
# =========================================================================

@app.route("/dashboard")
@login_required
def dashboard():
    """
    Show today's mess menu.

    TODO (DynamoDB): Fetch today's mess menu from DynamoDB.
      1. Import: from services.dynamodb import get_todays_menu
      2. Call:   menu = get_todays_menu()
      3. Pass `menu` to the template.

    The DynamoDB table (campus-hostel-mess-menu) should have one item per day
    with keys: day (PK), breakfast, lunch, snacks, dinner.
    """
    # Placeholder menu shown until DynamoDB is connected
    menu = {
        "breakfast": "Poha, Chai, Banana",
        "lunch":     "Rice, Dal, Sabzi, Roti, Salad",
        "snacks":    "Samosa, Tea",
        "dinner":    "Roti, Paneer Curry, Rice, Dal, Curd",
    }
    user = session.get("user", {})
    return render_template("dashboard.html", menu=menu, user=user)


@app.route("/complaints")
@login_required
def complaints():
    """
    Show the logged-in user's complaint history.

    TODO (DynamoDB): Fetch complaints from DynamoDB filtered by the current user.
      1. Import: from services.dynamodb import get_user_complaints
      2. Call:   user_complaints = get_user_complaints(user_id)
         where user_id = session["user"]["username"]
      3. Pass the list to the template.

    Each complaint item should have:
        complaint_id, title, category, description, status, created_at
    """
    user = session.get("user", {})
    # TODO (DynamoDB): Replace placeholder list with real data from DynamoDB.
    user_complaints = []  # Empty until DynamoDB is connected
    return render_template("complaints.html", complaints=user_complaints, user=user)


@app.route("/raise-complaint", methods=["GET", "POST"])
@login_required
def raise_complaint():
    """
    Display and process the raise-complaint form.

    TODO (DynamoDB): On POST, save the complaint to DynamoDB.
      1. Import: from services.dynamodb import create_complaint
      2. Build a complaint dict:
             {
               "complaint_id": str(uuid.uuid4()),
               "user_id":      session["user"]["username"],
               "title":        title,
               "category":     category,
               "description":  description,
               "status":       "Open",
               "created_at":   datetime.utcnow().isoformat(),
             }
      3. Call: create_complaint(complaint)
      4. Flash success and redirect to /complaints.
    """
    user = session.get("user", {})

    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        category    = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()

        if not title or not category or not description:
            flash("All fields are required.", "error")
            return render_template("raise_complaint.html", user=user)

        # -----------------------------------------------------------
        # TODO (DynamoDB): Save complaint to DynamoDB here.
        # -----------------------------------------------------------
        flash("Complaint submission is not yet connected to the database. Configure DynamoDB to enable this.", "warning")
        return render_template("raise_complaint.html", user=user)

    return render_template("raise_complaint.html", user=user)


@app.route("/announcements")
@login_required
def announcements():
    """
    Display hostel-wide announcements.

    TODO (DynamoDB): Fetch all announcements from DynamoDB, sorted newest first.
      1. Import: from services.dynamodb import get_announcements
      2. Call:   all_announcements = get_announcements()
      3. Pass the list to the template.

    Each announcement item should have:
        announcement_id, title, body, posted_by, created_at
    """
    user = session.get("user", {})
    # TODO (DynamoDB): Replace placeholder list with real data from DynamoDB.
    all_announcements = []  # Empty until DynamoDB is connected
    return render_template("announcements.html", announcements=all_announcements, user=user)


# =========================================================================
# Run the app
# =========================================================================
if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "True").lower() == "true"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)
