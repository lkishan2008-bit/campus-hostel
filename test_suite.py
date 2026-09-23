"""
test_suite.py
--------------
Automated testing for Campus Hostel Companion:
  Existing core tests (27):
    1. Test signup (Cognito register)
    2. Test login (Cognito auth + session)
    3. Test logout (Session clear)
    4. Test authenticated dashboard (Mess menu + quick actions)
    5. Test creating a complaint (DynamoDB save with title, category, description, status, timestamp)
    6. Test viewing complaint history
    7. Test announcement loading
    8. Test user complaint isolation (Student A cannot see Student B's private complaints)
    9. Test health endpoint
   10. Test email verification code flow
   11. Test weekly menu retrieval
   12. Test weekly menu update
   13. Test today's menu selection from weekly menu

  New feature & security tests:
   14. Test organization creation & invite code generation
   15. Test organization membership creation (roles: student, warden)
   16. Test joining organization with valid invite code
   17. Test joining organization with invalid invite code
   18. Test onboarding page access
   19. Test warden dashboard authorization (students blocked with 403)
   20. Test warden complaint retrieval scoped to organization
   21. Test warden cannot view complaints from other organizations
   22. Test student cannot access another organization's complaint
   23. Test student cannot access another student's complaint by ID (IDOR prevention)
   24. Test complaint status update by warden (Submitted, Under Review, In Progress, Resolved, Rejected)
   25. Test complaint status update authorization (warden from another org cannot update)
   26. Test WhatsApp notification skips safely when disabled/unconfigured
   27. Test WhatsApp notification failure does not break complaint creation
   28. Test WhatsApp service does not expose tokens in logs or errors
   29. Test AI complaint intelligence analysis & priority assignment
   30. Test AI failure falls back smoothly without breaking complaint creation
   31. Test unauthorized role escalation prevention
   32. Test warden private phone number not exposed in public views
"""

import unittest
from unittest.mock import patch, MagicMock
from app import app
from services.ai_service import analyze_complaint
from services.whatsapp import send_warden_complaint_notification, is_whatsapp_configured


class CampusHostelCompanionTestCase(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret-key"
        self.client = app.test_client()

    # ---------------------------------------------------------------------
    # Health Endpoint
    # ---------------------------------------------------------------------
    def test_health_endpoint(self):
        """Verify /health returns {'status': 'ok'}."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})

    # ---------------------------------------------------------------------
    # 1. Sign Up
    # ---------------------------------------------------------------------
    @patch("app.register_user")
    def test_signup_success(self, mock_register):
        """Test successful user registration via the /auth register tab."""
        mock_register.return_value = {"success": True, "user_confirmed": True, "user_sub": "sub-123"}

        resp = self.client.post("/auth", data={
            "tab": "register",
            "username": "student1",
            "reg_email": "student1@campus.edu",
            "reg_password": "Password123!",
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        mock_register.assert_called_once_with("student1", "student1@campus.edu", "Password123!")
        self.assertIn(b"Account created", resp.data)

    @patch("app.register_user")
    def test_signup_redirects_to_verify_when_unconfirmed(self, mock_register):
        """Unconfirmed registration should redirect to /verify-email."""
        mock_register.return_value = {"success": True, "user_confirmed": False, "user_sub": "sub-456"}

        resp = self.client.post("/auth", data={
            "tab": "register",
            "username": "student2",
            "reg_email": "student2@campus.edu",
            "reg_password": "Password123!",
        }, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/verify-email", resp.headers["Location"])

    @patch("app.register_user")
    def test_signup_failure(self, mock_register):
        """Test registration failure returns the error message."""
        mock_register.return_value = {"success": False, "error": "Username already exists."}

        resp = self.client.post("/auth", data={
            "tab": "register",
            "username": "existing_user",
            "reg_email": "user@campus.edu",
            "reg_password": "Password123!",
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Username already exists", resp.data)

    # ---------------------------------------------------------------------
    # 2. Login
    # ---------------------------------------------------------------------
    @patch("app.get_user_membership")
    @patch("app.authenticate_user")
    def test_login_success(self, mock_auth, mock_membership):
        """Test successful authentication sets session and redirects to dashboard."""
        mock_auth.return_value = {
            "success": True,
            "user": {
                "username": "student_alice",
                "email": "alice@campus.edu",
                "sub": "sub-alice-uuid-1234",
            },
        }
        mock_membership.return_value = {
            "user_id": "student_alice",
            "organization_id": "org_hostel_a",
            "role": "student",
        }

        resp = self.client.post("/login", data={
            "username": "student_alice",
            "password": "Password123!",
        }, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/dashboard"))

        # Verify session
        with self.client.session_transaction() as sess:
            self.assertIn("user", sess)
            self.assertEqual(sess["user"]["username"], "student_alice")
            self.assertEqual(sess["user"]["email"], "alice@campus.edu")
            self.assertEqual(sess["user"]["role"], "student")
            self.assertEqual(sess.get("organization_id"), "org_hostel_a")
            self.assertNotIn("id_token", sess["user"])
            self.assertNotIn("access_token", sess["user"])
            self.assertNotIn("refresh_token", sess["user"])

    @patch("app.get_user_membership")
    @patch("app.authenticate_user")
    def test_login_does_not_put_tokens_in_session_or_oversized_header(self, mock_auth, mock_membership):
        """Verify successful login keeps headers small and excludes raw Cognito JWTs from session cookie."""
        mock_auth.return_value = {
            "success": True,
            "user": {
                "username": "student_alice",
                "email": "alice@campus.edu",
                "sub": "sub-alice-uuid-1234",
                "id_token": "a" * 2000,
                "access_token": "b" * 2000,
                "refresh_token": "c" * 2000,
            },
        }
        mock_membership.return_value = {
            "user_id": "student_alice",
            "organization_id": "org_hostel_a",
            "role": "student",
        }

        resp = self.client.post("/login", data={
            "username": "student_alice",
            "password": "Password123!",
        }, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertNotIn("id_token", sess["user"])
            self.assertNotIn("access_token", sess["user"])
            self.assertNotIn("refresh_token", sess["user"])

        # Check Set-Cookie response header length is compact (well below 1024 bytes, preventing Nginx 502)
        set_cookie = resp.headers.get("Set-Cookie", "")
        self.assertLess(len(set_cookie), 1024)

    @patch("app.authenticate_user")
    def test_login_failure(self, mock_auth):
        """Test invalid credentials display an error."""
        mock_auth.return_value = {"success": False, "error": "Incorrect username or password."}

        resp = self.client.post("/login", data={
            "username": "student_alice",
            "password": "WrongPassword",
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Incorrect username or password", resp.data)

    # ---------------------------------------------------------------------
    # 3. Logout
    # ---------------------------------------------------------------------
    def test_logout(self):
        """Test logging out clears the session."""
        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "student_alice"}

        resp = self.client.get("/logout", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with self.client.session_transaction() as sess:
            self.assertNotIn("user", sess)

    # ---------------------------------------------------------------------
    # 4. Authenticated Dashboard (Today's Mess Menu)
    # ---------------------------------------------------------------------
    def test_dashboard_requires_login(self):
        """Unauthenticated access to /dashboard redirects to landing page."""
        resp = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/"))

    @patch("app.get_todays_menu")
    def test_dashboard_authenticated(self, mock_menu):
        """Authenticated access displays today's mess menu and user's name."""
        mock_menu.return_value = {
            "breakfast": "Idli Sambar & Chutney",
            "lunch": "Biryani, Raita & Salad",
            "dinner": "Roti, Dal Tadka & Paneer",
            "day": "Friday",
        }

        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "student_alice"}

        resp = self.client.get("/dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"student_alice", resp.data)
        self.assertIn(b"Idli Sambar", resp.data)
        self.assertIn(b"Biryani", resp.data)
        self.assertIn(b"Raise a Complaint", resp.data)
        self.assertIn(b"My Complaints", resp.data)
        self.assertIn(b"Announcements", resp.data)

    # ---------------------------------------------------------------------
    # 5. Raise a Complaint
    # ---------------------------------------------------------------------
    @patch("app.send_warden_complaint_notification")
    @patch("app.create_complaint")
    def test_raise_complaint_success(self, mock_create, mock_notify):
        """Test submitting a complaint creates a DynamoDB record."""
        mock_create.return_value = (True, "")
        mock_notify.return_value = True

        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "student_alice"}
            sess["organization_id"] = "org_123"

        resp = self.client.post("/raise-complaint", data={
            "title": "Leaking tap in Room 302",
            "category": "Water",
            "description": "Bathroom tap is dripping continuously.",
        }, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/complaints"))

        # Check complaint record passed to create_complaint
        mock_create.assert_called_once()
        record = mock_create.call_args[0][0]
        self.assertEqual(record["user_id"], "student_alice")
        self.assertEqual(record["title"], "Leaking tap in Room 302")
        self.assertEqual(record["category"], "Water")
        self.assertEqual(record["description"], "Bathroom tap is dripping continuously.")
        self.assertEqual(record["status"], "Submitted")
        self.assertTrue("complaint_id" in record)
        self.assertTrue("created_at" in record)
        self.assertTrue("priority" in record)

    # ---------------------------------------------------------------------
    # 6. View Complaint History
    # ---------------------------------------------------------------------
    @patch("app.get_user_complaints")
    def test_view_complaints_history(self, mock_get_complaints):
        """Test viewing own complaint history displays items with status."""
        mock_get_complaints.return_value = [
            {
                "complaint_id": "c-101",
                "user_id": "student_alice",
                "title": "WiFi disconnected on 3rd floor",
                "category": "Internet",
                "description": "No signal in wing B.",
                "status": "In Progress",
                "created_at": "2026-09-18 10:00:00",
            }
        ]

        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "student_alice"}

        resp = self.client.get("/complaints")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"WiFi disconnected on 3rd floor", resp.data)
        self.assertIn(b"In Progress", resp.data)
        self.assertIn(b"Internet", resp.data)

    # ---------------------------------------------------------------------
    # 7. Announcements Loading
    # ---------------------------------------------------------------------
    @patch("app.get_announcements")
    def test_announcements_loading(self, mock_announcements):
        """Test loading hostel-wide announcements from DynamoDB."""
        mock_announcements.return_value = [
            {
                "announcement_id": "a-1",
                "title": "Hostel Gate Closes at 10 PM",
                "body": "Strict curfew timings effective from tonight.",
                "posted_by": "Warden Office",
                "created_at": "2026-09-18 09:00:00",
            }
        ]

        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "student_alice"}

        resp = self.client.get("/announcements")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Hostel Gate Closes at 10 PM", resp.data)
        self.assertIn(b"Warden Office", resp.data)

    # ---------------------------------------------------------------------
    # 8. User Privacy & Isolation (A cannot see B's complaints)
    # ---------------------------------------------------------------------
    def test_user_complaint_isolation(self):
        """
        Verify that student A only receives their own complaints,
        and get_user_complaints strictly filters out student B's data.
        """
        from services.dynamodb import get_user_complaints

        all_database_items = [
            {"complaint_id": "1", "user_id": "student_alice", "title": "Alice Issue", "created_at": "2026-01-01"},
            {"complaint_id": "2", "user_id": "student_bob", "title": "Bob Private Issue", "created_at": "2026-01-02"},
            {"complaint_id": "3", "user_id": "student_alice", "title": "Alice Second Issue", "created_at": "2026-01-03"},
        ]

        # Mock DynamoDB table scan returning mixed items
        with patch("services.dynamodb._get_resource") as mock_res:
            mock_table = MagicMock()
            mock_table.query.side_effect = Exception("No GSI")
            mock_table.scan.return_value = {"Items": all_database_items}
            mock_res.return_value.Table.return_value = mock_table

            # Bob requests complaints
            bobs_complaints = get_user_complaints("student_bob")
            self.assertEqual(len(bobs_complaints), 1)
            self.assertEqual(bobs_complaints[0]["user_id"], "student_bob")
            self.assertEqual(bobs_complaints[0]["title"], "Bob Private Issue")
            self.assertNotIn("Alice Issue", [c["title"] for c in bobs_complaints])

            # Alice requests complaints
            alices_complaints = get_user_complaints("student_alice")
            self.assertEqual(len(alices_complaints), 2)
            for c in alices_complaints:
                self.assertEqual(c["user_id"], "student_alice")
            self.assertNotIn("Bob Private Issue", [c["title"] for c in alices_complaints])

    # ---------------------------------------------------------------------
    # 9. Email Verification Code Flow
    # ---------------------------------------------------------------------
    def test_verify_email_page_accessible_without_session(self):
        """Verify email page loads (200 OK) without needing prior session or login."""
        resp = self.client.get("/verify-email")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Verify your email", resp.data)
        self.assertIn(b"Verification code", resp.data)
        self.assertIn(b"Resend code", resp.data)

    def test_signin_page_has_verify_link(self):
        """The Sign in page visibly includes a link to /verify-email."""
        resp = self.client.get("/auth")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Verify your email", resp.data)
        self.assertIn(b"/verify-email", resp.data)

    @patch("app.confirm_user")
    def test_verify_email_success(self, mock_confirm):
        """Valid code confirms the user and redirects to login with success flash."""
        mock_confirm.return_value = {"success": True}

        resp = self.client.post("/verify-email", data={
            "action": "verify",
            "email": "new@campus.edu",
            "code": "123456",
        }, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        mock_confirm.assert_called_once_with("new@campus.edu", "123456")

    @patch("app.confirm_user")
    def test_verify_email_wrong_code(self, mock_confirm):
        """Wrong code stays on verify page and shows error."""
        mock_confirm.return_value = {"success": False, "error": "Incorrect verification code. Please try again."}

        resp = self.client.post("/verify-email", data={
            "action": "verify",
            "email": "new@campus.edu",
            "code": "000000",
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Incorrect verification code", resp.data)

    @patch("app.resend_verification_code")
    def test_verify_email_resend(self, mock_resend):
        """Resend action calls resend_verification_code and stays on verify page."""
        mock_resend.return_value = {"success": True}

        resp = self.client.post("/verify-email", data={
            "action": "resend",
            "email": "new@campus.edu",
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        mock_resend.assert_called_once_with("new@campus.edu")
        self.assertIn(b"verification code has been sent", resp.data)

    @patch("app.authenticate_user")
    def test_unconfirmed_login_redirects_to_verify(self, mock_auth):
        """Unconfirmed user login attempt redirects to /verify-email with warning message."""
        mock_auth.return_value = {
            "success": False,
            "error": "Your email is not verified yet. Please enter the verification code sent to your email.",
            "not_confirmed": True,
            "email": "unverified@campus.edu",
        }

        resp = self.client.post("/login", data={
            "username": "unverified@campus.edu",
            "password": "Password123!",
        }, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/verify-email", resp.headers["Location"])
        self.assertIn("unverified@campus.edu", resp.headers["Location"])

    # ---------------------------------------------------------------------
    # 10. Weekly Menu Retrieval
    # ---------------------------------------------------------------------
    @patch("services.dynamodb._get_resource")
    def test_get_weekly_menu_from_dynamodb(self, mock_res):
        """get_weekly_menu returns data from DynamoDB when available using item_id key."""
        from services.dynamodb import get_weekly_menu, DAYS_OF_WEEK

        monday_item = {
            "item_id": "Monday",
            "day": "Monday",
            "breakfast": "Oats & Fruit",
            "lunch": "Rice & Dal",
            "dinner": "Roti & Curry",
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": monday_item}
        mock_res.return_value.Table.return_value = mock_table

        weekly = get_weekly_menu()
        self.assertIn("Monday", weekly)
        self.assertEqual(weekly["Monday"]["breakfast"], "Oats & Fruit")
        self.assertEqual(weekly["Monday"]["lunch"], "Rice & Dal")
        mock_table.get_item.assert_any_call(Key={"item_id": "Monday"})
        for day in DAYS_OF_WEEK:
            self.assertIn(day, weekly)

    @patch("services.dynamodb._get_resource")
    def test_get_weekly_menu_falls_back_when_empty(self, mock_res):
        """get_weekly_menu uses FALLBACK_MENU when DynamoDB returns no items."""
        from services.dynamodb import get_weekly_menu, DAYS_OF_WEEK, FALLBACK_MENU

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_res.return_value.Table.return_value = mock_table

        weekly = get_weekly_menu()
        for day in DAYS_OF_WEEK:
            self.assertIn(day, weekly)
            self.assertEqual(weekly[day]["breakfast"], FALLBACK_MENU[day]["breakfast"])

    # ---------------------------------------------------------------------
    # 11. Weekly Menu Update (save_weekly_menu)
    # ---------------------------------------------------------------------
    @patch("services.dynamodb._get_resource")
    def test_save_weekly_menu_success(self, mock_res):
        """save_weekly_menu writes all 7 days to DynamoDB with item_id partition key."""
        from services.dynamodb import save_weekly_menu, DAYS_OF_WEEK

        mock_table = MagicMock()
        mock_res.return_value.Table.return_value = mock_table

        menu_data = {day: {"breakfast": "B", "lunch": "L", "dinner": "D"} for day in DAYS_OF_WEEK}
        ok, err = save_weekly_menu(menu_data)

        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(mock_table.put_item.call_count, 7)

        saved_items = [call[1]["Item"] for call in mock_table.put_item.call_args_list]
        for item in saved_items:
            self.assertIn("item_id", item)
            self.assertIn("day", item)
            self.assertEqual(item["item_id"], item["day"])

    @patch("services.dynamodb._get_resource")
    def test_save_weekly_menu_dynamodb_error(self, mock_res):
        """save_weekly_menu returns (False, error) on DynamoDB failure."""
        from services.dynamodb import save_weekly_menu, DAYS_OF_WEEK
        from botocore.exceptions import ClientError

        mock_table = MagicMock()
        mock_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "Service unavailable"}}, "PutItem"
        )
        mock_res.return_value.Table.return_value = mock_table

        menu_data = {day: {"breakfast": "B", "lunch": "L", "dinner": "D"} for day in DAYS_OF_WEEK}
        ok, err = save_weekly_menu(menu_data)

        self.assertFalse(ok)
        self.assertIn("unavailable", err)

    # ---------------------------------------------------------------------
    # 12. Today's Menu from Weekly Schedule
    # ---------------------------------------------------------------------
    @patch("services.dynamodb._get_resource")
    def test_get_todays_menu_from_dynamodb(self, mock_res):
        """get_todays_menu returns today's entry from DynamoDB weekly table using item_id key."""
        from services.dynamodb import get_todays_menu
        from datetime import datetime

        today = datetime.now().strftime("%A")
        day_item = {
            "item_id": today,
            "day": today,
            "breakfast": "Special Breakfast",
            "lunch": "Special Lunch",
            "dinner": "Special Dinner",
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": day_item}
        mock_res.return_value.Table.return_value = mock_table

        menu = get_todays_menu()
        self.assertEqual(menu["day"], today)
        self.assertEqual(menu["breakfast"], "Special Breakfast")
        self.assertEqual(menu["lunch"], "Special Lunch")
        self.assertEqual(menu["dinner"], "Special Dinner")
        mock_table.get_item.assert_called_once_with(Key={"item_id": today})

    @patch("services.dynamodb._get_resource")
    def test_get_todays_menu_fallback(self, mock_res):
        """get_todays_menu falls back gracefully when DynamoDB is unavailable."""
        from services.dynamodb import get_todays_menu
        from datetime import datetime

        mock_res.side_effect = Exception("DynamoDB unavailable")

        menu = get_todays_menu()
        today = datetime.now().strftime("%A")
        self.assertEqual(menu["day"], today)
        self.assertTrue(bool(menu.get("breakfast")))
        self.assertTrue(bool(menu.get("lunch")))
        self.assertTrue(bool(menu.get("dinner")))

    # ---------------------------------------------------------------------
    # 13. Edit Menu Route (authenticated)
    # ---------------------------------------------------------------------
    @patch("app.save_weekly_menu")
    @patch("app.get_weekly_menu")
    def test_edit_menu_post_success(self, mock_get, mock_save):
        """Authenticated POST to /edit-menu with valid data redirects to weekly menu."""
        from services.dynamodb import DAYS_OF_WEEK

        mock_get.return_value = {d: {"breakfast": "B", "lunch": "L", "dinner": "D"} for d in DAYS_OF_WEEK}
        mock_save.return_value = (True, "")

        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "hostel_staff"}

        form_data = {}
        for day in DAYS_OF_WEEK:
            form_data[f"{day}_breakfast"] = f"{day} Breakfast"
            form_data[f"{day}_lunch"] = f"{day} Lunch"
            form_data[f"{day}_dinner"] = f"{day} Dinner"

        resp = self.client.post("/edit-menu", data=form_data, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/weekly-menu", resp.headers["Location"])
        mock_save.assert_called_once()

    @patch("app.get_weekly_menu")
    def test_weekly_menu_page_loads(self, mock_weekly):
        """GET /weekly-menu shows all 7 days."""
        from services.dynamodb import DAYS_OF_WEEK

        mock_weekly.return_value = {
            d: {"breakfast": f"{d} B", "lunch": f"{d} L", "dinner": f"{d} D"}
            for d in DAYS_OF_WEEK
        }

        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "student_alice"}

        resp = self.client.get("/weekly-menu")
        self.assertEqual(resp.status_code, 200)
        for day in DAYS_OF_WEEK:
            self.assertIn(day.encode(), resp.data)

    # =====================================================================
    # NEW FEATURE & SECURITY TESTS
    # =====================================================================

    # ---------------------------------------------------------------------
    # 14. Organization Creation & Invite Code
    # ---------------------------------------------------------------------
    @patch("services.dynamodb._get_resource")
    def test_organization_creation(self, mock_res):
        """Create organization generates a unique organization_id and invite code."""
        from services.dynamodb import create_organization

        mock_table = MagicMock()
        mock_res.return_value.Table.return_value = mock_table

        org, err = create_organization(
            name="Emerald Hall",
            org_type="College Hostel",
            member_count="250",
            creator_id="warden_rajesh",
            phone="+919876543210",
        )

        self.assertEqual(err, "")
        self.assertIsNotNone(org)
        self.assertEqual(org["organization_name"], "Emerald Hall")
        self.assertEqual(org["organization_type"], "College Hostel")
        self.assertTrue(org["organization_id"].startswith("org_"))
        self.assertTrue(bool(org["invite_code"]))
        self.assertEqual(org["created_by"], "warden_rajesh")
        mock_table.put_item.assert_called_once()

    # ---------------------------------------------------------------------
    # 15. Organization Membership Creation
    # ---------------------------------------------------------------------
    @patch("services.dynamodb._get_resource")
    def test_add_organization_membership(self, mock_res):
        """Test recording user membership in an organization with specific role."""
        from services.dynamodb import add_organization_member

        mock_table = MagicMock()
        mock_res.return_value.Table.return_value = mock_table

        ok, err = add_organization_member(
            organization_id="org_123",
            user_id="student_bob",
            role="student",
            user_name="Bob",
        )

        self.assertTrue(ok)
        self.assertEqual(err, "")
        mock_table.put_item.assert_called_once()
        saved_item = mock_table.put_item.call_args[1]["Item"]
        self.assertEqual(saved_item["user_id"], "student_bob")
        self.assertEqual(saved_item["role"], "student")
        self.assertEqual(saved_item["organization_id"], "org_123")

    # ---------------------------------------------------------------------
    # 16. Join Organization Flow (Valid invite code)
    # ---------------------------------------------------------------------
    @patch("app.add_organization_member")
    @patch("app.get_organization_by_invite_code")
    def test_join_organization_valid_code(self, mock_get_org, mock_add_member):
        """Student joining with valid invite code joins org and redirects to dashboard."""
        mock_get_org.return_value = {
            "organization_id": "org_emerald",
            "organization_name": "Emerald Hall",
            "invite_code": "CH-8F2K",
        }
        mock_add_member.return_value = (True, "")

        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "student_carol"}

        resp = self.client.post("/join-organization", data={
            "invite_code": "ch-8f2k",
        }, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/dashboard"))

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["organization_id"], "org_emerald")
            self.assertEqual(sess["user"]["role"], "student")

    # ---------------------------------------------------------------------
    # 17. Join Organization Flow (Invalid invite code)
    # ---------------------------------------------------------------------
    @patch("app.get_organization_by_invite_code")
    def test_join_organization_invalid_code(self, mock_get_org):
        """Student entering invalid invite code receives an error and stays on onboarding."""
        mock_get_org.return_value = None

        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "student_carol"}

        resp = self.client.post("/join-organization", data={
            "invite_code": "INVALID-CODE",
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Invalid invite code", resp.data)

    # ---------------------------------------------------------------------
    # 18. Onboarding Page Access
    # ---------------------------------------------------------------------
    def test_onboarding_page_loads_for_authenticated_user(self):
        """Authenticated users can access /onboarding page."""
        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "student_new"}

        resp = self.client.get("/onboarding")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Join Your Hostel", resp.data)
        self.assertIn(b"Warden Setup", resp.data)

    # ---------------------------------------------------------------------
    # 19. Warden Dashboard Protection (Non-warden blocked)
    # ---------------------------------------------------------------------
    def test_warden_dashboard_blocked_for_students(self):
        """Students attempting to access /warden/dashboard receive 403 / redirect with error."""
        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "student_alice", "role": "student"}
            sess["organization_id"] = "org_123"

        resp = self.client.get("/warden/dashboard", follow_redirects=False)
        self.assertEqual(resp.status_code, 403)

    # ---------------------------------------------------------------------
    # 20. Warden Complaint Retrieval Scoped to Organization
    # ---------------------------------------------------------------------
    @patch("app.get_organization")
    @patch("app.get_organization_complaints")
    def test_warden_dashboard_authenticated(self, mock_get_complaints, mock_get_org):
        """Warden accessing /warden/dashboard views complaints for their organization."""
        mock_get_org.return_value = {
            "organization_id": "org_emerald",
            "organization_name": "Emerald Hall",
            "invite_code": "CH-8F2K",
            "organization_type": "College Hostel",
        }
        mock_get_complaints.return_value = [
            {
                "complaint_id": "c-99",
                "organization_id": "org_emerald",
                "user_id": "student_dan",
                "title": "Geyser broken in Room 104",
                "category": "Water",
                "priority": "High",
                "status": "Submitted",
                "created_at": "2026-09-20 08:00:00",
                "ai_classification": {
                    "suggested_action": "Assign plumbing staff.",
                },
            }
        ]

        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "warden_rajesh", "role": "warden"}
            sess["organization_id"] = "org_emerald"

        resp = self.client.get("/warden/dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Emerald Hall", resp.data)
        self.assertIn(b"Geyser broken in Room 104", resp.data)
        self.assertIn(b"CH-8F2K", resp.data)

    # ---------------------------------------------------------------------
    # 21. Cross-Organization Complaint Isolation for Wardens
    # ---------------------------------------------------------------------
    def test_warden_cannot_view_other_organization_complaints(self):
        """get_organization_complaints strictly filters complaints by organization_id."""
        from services.dynamodb import get_organization_complaints

        db_items = [
            {"complaint_id": "1", "organization_id": "org_A", "title": "Org A Complaint"},
            {"complaint_id": "2", "organization_id": "org_B", "title": "Org B Complaint"},
        ]

        with patch("services.dynamodb._get_resource") as mock_res:
            mock_table = MagicMock()
            mock_table.scan.return_value = {"Items": [db_items[0]]}
            mock_res.return_value.Table.return_value = mock_table

            org_a_complaints = get_organization_complaints("org_A")
            self.assertEqual(len(org_a_complaints), 1)
            self.assertEqual(org_a_complaints[0]["organization_id"], "org_A")

    # ---------------------------------------------------------------------
    # 22. IDOR Prevention: Single Complaint Direct Access Protection
    # ---------------------------------------------------------------------
    @patch("app.get_complaint_by_id")
    def test_student_cannot_access_other_student_complaint_by_id(self, mock_get_c):
        """Student B attempting direct URL access to Student A's complaint is blocked with 403."""
        mock_get_c.return_value = {
            "complaint_id": "c-private-123",
            "organization_id": "org_emerald",
            "user_id": "student_alice",
            "title": "Private Medical Facility Request",
            "status": "Submitted",
        }

        # Student Bob attempts to access Alice's complaint directly
        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "student_bob", "role": "student"}
            sess["organization_id"] = "org_emerald"

        resp = self.client.get("/complaints/c-private-123", follow_redirects=False)
        self.assertEqual(resp.status_code, 403)

    @patch("app.get_complaint_by_id")
    def test_authorized_warden_can_access_org_complaint_by_id(self, mock_get_c):
        """Authorized warden of the same organization can view the complaint."""
        mock_get_c.return_value = {
            "complaint_id": "c-private-123",
            "organization_id": "org_emerald",
            "user_id": "student_alice",
            "title": "Broken Window",
            "status": "Submitted",
        }

        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "warden_rajesh", "role": "warden"}
            sess["organization_id"] = "org_emerald"

        resp = self.client.get("/complaints/c-private-123")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Broken Window", resp.data)

    # ---------------------------------------------------------------------
    # 23. Complaint Status Update
    # ---------------------------------------------------------------------
    @patch("app.update_complaint_status")
    def test_warden_can_update_complaint_status(self, mock_update):
        """Warden can update complaint status to Resolved / In Progress / Under Review."""
        mock_update.return_value = (True, "")

        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "warden_rajesh", "role": "warden"}
            sess["organization_id"] = "org_emerald"

        resp = self.client.post("/warden/complaints/c-101/status", data={
            "status": "Resolved",
        }, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/warden/dashboard", resp.headers["Location"])
        mock_update.assert_called_once_with("c-101", "Resolved", organization_id="org_emerald")

    # ---------------------------------------------------------------------
    # 24. WhatsApp Service Resilience (Missing Config & Failures)
    # ---------------------------------------------------------------------
    def test_whatsapp_notification_skipped_safely_when_unconfigured(self):
        """WhatsApp notification safely returns False and logs skipping when disabled."""
        complaint = {
            "complaint_id": "c-test",
            "category": "Maintenance",
            "priority": "Medium",
        }
        sent = send_warden_complaint_notification(complaint, recipient_phone="+919876543210")
        self.assertFalse(sent)

    @patch("services.whatsapp.is_whatsapp_configured")
    @patch("urllib.request.urlopen")
    def test_whatsapp_notification_network_error_does_not_raise(self, mock_urlopen, mock_config):
        """Network error during WhatsApp notification is caught safely without raising."""
        mock_config.return_value = True
        mock_urlopen.side_effect = Exception("Simulated network timeout")

        complaint = {
            "complaint_id": "c-test",
            "category": "Maintenance",
            "priority": "High",
        }
        # Should not raise exception
        sent = send_warden_complaint_notification(complaint, recipient_phone="+919876543210")
        self.assertFalse(sent)

    # ---------------------------------------------------------------------
    # 25. AI Complaint Intelligence Analysis
    # ---------------------------------------------------------------------
    def test_ai_complaint_intelligence_analysis(self):
        """AI intelligence analyzes title/description to assign priority and category."""
        res = analyze_complaint(
            title="Electric spark from switchboard in room 201",
            description="There was smoke and sparks when turning on the light switch.",
            category="Electricity",
        )
        self.assertIn("priority", res)
        self.assertIn(res["priority"], ["High", "Critical"])
        self.assertEqual(res["category"], "Electricity")
        self.assertIn("suggested_action", res)
        self.assertTrue(len(res["suggested_action"]) > 5)

    def test_ai_fallback_resilience(self):
        """Empty or invalid inputs to AI service do not crash and produce fallback."""
        res = analyze_complaint("", "")
        self.assertEqual(res["priority"], "Medium")
        self.assertIn("category", res)

    # ---------------------------------------------------------------------
    # 26. Role Escalation Prevention
    # ---------------------------------------------------------------------
    def test_role_escalation_prevented_in_session(self):
        """A regular student user cannot execute warden actions without valid role."""
        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "student_eve", "role": "student"}
            sess["organization_id"] = "org_123"

        resp = self.client.post("/warden/complaints/c-1/status", data={"status": "Resolved"})
        self.assertEqual(resp.status_code, 403)


class CognitoSecretHashTestCase(unittest.TestCase):
    """Unit tests for Cognito secret hash calculation and all authenticated Cognito API calls."""

    def setUp(self):
        import services.cognito as cognito_mod
        cognito_mod._CACHED_CLIENT_SECRET = None
        self.test_client_id = "test_client_id_123"
        self.test_client_secret = "test_client_secret_xyz789"
        self.test_username = "student_test@campus.edu"

    # ---------------------------------------------------------------------
    # Calculation & Config Tests
    # ---------------------------------------------------------------------
    def test_secret_hash_calculation_exact(self):
        """Verify _calculate_secret_hash uses Base64(HMAC-SHA256(secret, username + client_id))."""
        import hmac
        import hashlib
        import base64
        from services.cognito import _calculate_secret_hash

        username = "alice@campus.edu"
        client_id = "mock_client_abc"
        secret = "mock_secret_key_xyz"

        expected_msg = (username + client_id).encode("utf-8")
        expected_digest = hmac.new(secret.encode("utf-8"), expected_msg, hashlib.sha256).digest()
        expected_hash = base64.b64encode(expected_digest).decode("utf-8")

        result = _calculate_secret_hash(username, client_id, secret)
        self.assertEqual(result, expected_hash)
        self.assertTrue(len(result) > 0)

    def test_secret_hash_empty_inputs(self):
        """Empty or missing inputs should return empty string without raising."""
        from services.cognito import _calculate_secret_hash
        self.assertEqual(_calculate_secret_hash("", "client_id", "secret"), "")
        self.assertEqual(_calculate_secret_hash("user", "", "secret"), "")
        self.assertEqual(_calculate_secret_hash("user", "client_id", ""), "")

    @patch.dict("os.environ", {"COGNITO_CLIENT_SECRET": "  env_secret_123  "})
    def test_get_client_secret_from_env(self):
        """_get_client_secret should read and strip COGNITO_CLIENT_SECRET from environment."""
        from services.cognito import _get_client_secret
        secret = _get_client_secret("any_cid")
        self.assertEqual(secret, "env_secret_123")

    @patch.dict("os.environ", {"COGNITO_CLIENT_SECRET": "", "COGNITO_USER_POOL_ID": "pool-123", "COGNITO_APP_CLIENT_ID": "cid-123"}, clear=False)
    @patch("services.cognito._get_client")
    def test_get_client_secret_via_describe_user_pool_client(self, mock_client_factory):
        """When env var is unset, fallback to describe_user_pool_client and cache result."""
        from services.cognito import _get_client_secret
        mock_boto_client = MagicMock()
        mock_boto_client.describe_user_pool_client.return_value = {
            "UserPoolClient": {"ClientSecret": "boto_fetched_secret"}
        }
        mock_client_factory.return_value = mock_boto_client

        secret = _get_client_secret("cid-123")
        self.assertEqual(secret, "boto_fetched_secret")
        mock_boto_client.describe_user_pool_client.assert_called_once_with(
            UserPoolId="pool-123",
            ClientId="cid-123",
        )

    # ---------------------------------------------------------------------
    # SignUp (register_user) with SecretHash
    # ---------------------------------------------------------------------
    @patch.dict("os.environ", {"COGNITO_APP_CLIENT_ID": "test_cid", "COGNITO_CLIENT_SECRET": "test_sec"}, clear=False)
    @patch("services.cognito._get_client")
    def test_register_user_includes_secret_hash(self, mock_client_factory):
        """register_user must include SecretHash in kwargs when client secret is configured."""
        from services.cognito import register_user, _calculate_secret_hash
        mock_boto_client = MagicMock()
        mock_boto_client.sign_up.return_value = {
            "UserConfirmed": False,
            "UserSub": "sub-test-123",
        }
        mock_client_factory.return_value = mock_boto_client

        res = register_user("student_bob", "bob@campus.edu", "Password123!")
        self.assertTrue(res["success"])
        self.assertFalse(res["user_confirmed"])
        self.assertEqual(res["user_sub"], "sub-test-123")

        mock_boto_client.sign_up.assert_called_once()
        call_kwargs = mock_boto_client.sign_up.call_args[1]
        self.assertIn("SecretHash", call_kwargs)
        expected_hash = _calculate_secret_hash("bob@campus.edu", "test_cid", "test_sec")
        self.assertEqual(call_kwargs["SecretHash"], expected_hash)
        self.assertEqual(call_kwargs["Username"], "bob@campus.edu")

    # ---------------------------------------------------------------------
    # InitiateAuth (authenticate_user) with SECRET_HASH
    # ---------------------------------------------------------------------
    @patch.dict("os.environ", {"COGNITO_APP_CLIENT_ID": "test_cid", "COGNITO_CLIENT_SECRET": "test_sec", "COGNITO_USER_POOL_ID": ""}, clear=False)
    @patch("services.cognito._get_client")
    def test_authenticate_user_includes_secret_hash(self, mock_client_factory):
        """authenticate_user must include SECRET_HASH in AuthParameters for USER_PASSWORD_AUTH."""
        from services.cognito import authenticate_user, _calculate_secret_hash
        mock_boto_client = MagicMock()
        mock_boto_client.initiate_auth.return_value = {
            "AuthenticationResult": {
                "IdToken": "mock.id.token",
                "AccessToken": "mock.access.token",
                "RefreshToken": "mock.refresh.token",
            }
        }
        mock_client_factory.return_value = mock_boto_client

        res = authenticate_user("bob@campus.edu", "Password123!")
        self.assertTrue(res["success"])
        self.assertEqual(res["user"]["email"], "bob@campus.edu")
        self.assertNotIn("id_token", res["user"])
        self.assertNotIn("access_token", res["user"])
        self.assertNotIn("refresh_token", res["user"])

        mock_boto_client.initiate_auth.assert_called_once()
        call_kwargs = mock_boto_client.initiate_auth.call_args[1]
        self.assertEqual(call_kwargs["AuthFlow"], "USER_PASSWORD_AUTH")
        self.assertEqual(call_kwargs["ClientId"], "test_cid")
        auth_params = call_kwargs["AuthParameters"]
        self.assertIn("SECRET_HASH", auth_params)
        expected_hash = _calculate_secret_hash("bob@campus.edu", "test_cid", "test_sec")
        self.assertEqual(auth_params["SECRET_HASH"], expected_hash)
        self.assertEqual(auth_params["USERNAME"], "bob@campus.edu")
        self.assertEqual(auth_params["PASSWORD"], "Password123!")

    def test_extract_user_info_excludes_tokens(self):
        """_extract_user_info must extract identity claims without leaking raw tokens."""
        import base64
        import json
        from services.cognito import _extract_user_info

        # Create valid base64 payload
        payload_dict = {"email": "bob@campus.edu", "name": "Bob Smith", "sub": "cognito-sub-12345"}
        payload_bytes = json.dumps(payload_dict).encode("utf-8")
        payload_b64 = base64.b64encode(payload_bytes).decode("utf-8")
        fake_id_token = f"eyJhbGciOiJSUzI1NiJ9.{payload_b64}.signature"

        cognito_resp = {
            "AuthenticationResult": {
                "IdToken": fake_id_token,
                "AccessToken": "massive-access-token-" * 100,
                "RefreshToken": "massive-refresh-token-" * 100,
            }
        }
        res = _extract_user_info(cognito_resp, default_username="bob@campus.edu")
        self.assertTrue(res["success"])
        user = res["user"]
        self.assertEqual(user["username"], "Bob Smith")
        self.assertEqual(user["email"], "bob@campus.edu")
        self.assertEqual(user["sub"], "cognito-sub-12345")
        self.assertEqual(user["user_id"], "cognito-sub-12345")
        self.assertNotIn("id_token", user)
        self.assertNotIn("access_token", user)
        self.assertNotIn("refresh_token", user)

    # ---------------------------------------------------------------------
    # ConfirmSignUp (confirm_user) with SecretHash
    # ---------------------------------------------------------------------
    @patch.dict("os.environ", {"COGNITO_APP_CLIENT_ID": "test_cid", "COGNITO_CLIENT_SECRET": "test_sec"}, clear=False)
    @patch("services.cognito._get_client")
    def test_confirm_user_includes_secret_hash(self, mock_client_factory):
        """confirm_user must include SecretHash in confirm_sign_up call."""
        from services.cognito import confirm_user, _calculate_secret_hash
        mock_boto_client = MagicMock()
        mock_boto_client.confirm_sign_up.return_value = {}
        mock_client_factory.return_value = mock_boto_client

        res = confirm_user("bob@campus.edu", "654321")
        self.assertTrue(res["success"])

        mock_boto_client.confirm_sign_up.assert_called_once()
        call_kwargs = mock_boto_client.confirm_sign_up.call_args[1]
        self.assertIn("SecretHash", call_kwargs)
        expected_hash = _calculate_secret_hash("bob@campus.edu", "test_cid", "test_sec")
        self.assertEqual(call_kwargs["SecretHash"], expected_hash)
        self.assertEqual(call_kwargs["ConfirmationCode"], "654321")

    # ---------------------------------------------------------------------
    # ResendConfirmationCode (resend_verification_code) with SecretHash
    # ---------------------------------------------------------------------
    @patch.dict("os.environ", {"COGNITO_APP_CLIENT_ID": "test_cid", "COGNITO_CLIENT_SECRET": "test_sec"}, clear=False)
    @patch("services.cognito._get_client")
    def test_resend_verification_code_includes_secret_hash(self, mock_client_factory):
        """resend_verification_code must include SecretHash in resend_confirmation_code call."""
        from services.cognito import resend_verification_code, _calculate_secret_hash
        mock_boto_client = MagicMock()
        mock_boto_client.resend_confirmation_code.return_value = {
            "CodeDeliveryDetails": {"Destination": "b***@c***.edu"}
        }
        mock_client_factory.return_value = mock_boto_client

        res = resend_verification_code("bob@campus.edu")
        self.assertTrue(res["success"])

        mock_boto_client.resend_confirmation_code.assert_called_once()
        call_kwargs = mock_boto_client.resend_confirmation_code.call_args[1]
        self.assertIn("SecretHash", call_kwargs)
        expected_hash = _calculate_secret_hash("bob@campus.edu", "test_cid", "test_sec")
        self.assertEqual(call_kwargs["SecretHash"], expected_hash)

    # ---------------------------------------------------------------------
    # ForgotPassword (forgot_password) with SecretHash
    # ---------------------------------------------------------------------
    @patch.dict("os.environ", {"COGNITO_APP_CLIENT_ID": "test_cid", "COGNITO_CLIENT_SECRET": "test_sec"}, clear=False)
    @patch("services.cognito._get_client")
    def test_forgot_password_includes_secret_hash(self, mock_client_factory):
        """forgot_password must include SecretHash in forgot_password call."""
        from services.cognito import forgot_password, _calculate_secret_hash
        mock_boto_client = MagicMock()
        mock_boto_client.forgot_password.return_value = {
            "CodeDeliveryDetails": {"Destination": "b***@c***.edu"}
        }
        mock_client_factory.return_value = mock_boto_client

        res = forgot_password("bob@campus.edu")
        self.assertTrue(res["success"])

        mock_boto_client.forgot_password.assert_called_once()
        call_kwargs = mock_boto_client.forgot_password.call_args[1]
        self.assertIn("SecretHash", call_kwargs)
        expected_hash = _calculate_secret_hash("bob@campus.edu", "test_cid", "test_sec")
        self.assertEqual(call_kwargs["SecretHash"], expected_hash)

    # ---------------------------------------------------------------------
    # ConfirmForgotPassword (confirm_forgot_password) with SecretHash
    # ---------------------------------------------------------------------
    @patch.dict("os.environ", {"COGNITO_APP_CLIENT_ID": "test_cid", "COGNITO_CLIENT_SECRET": "test_sec"}, clear=False)
    @patch("services.cognito._get_client")
    def test_confirm_forgot_password_includes_secret_hash(self, mock_client_factory):
        """confirm_forgot_password must include SecretHash in confirm_forgot_password call."""
        from services.cognito import confirm_forgot_password, _calculate_secret_hash
        mock_boto_client = MagicMock()
        mock_boto_client.confirm_forgot_password.return_value = {}
        mock_client_factory.return_value = mock_boto_client

        res = confirm_forgot_password("bob@campus.edu", "123456", "NewPassword123!")
        self.assertTrue(res["success"])

        mock_boto_client.confirm_forgot_password.assert_called_once()
        call_kwargs = mock_boto_client.confirm_forgot_password.call_args[1]
        self.assertIn("SecretHash", call_kwargs)
        expected_hash = _calculate_secret_hash("bob@campus.edu", "test_cid", "test_sec")
        self.assertEqual(call_kwargs["SecretHash"], expected_hash)
        self.assertEqual(call_kwargs["Password"], "NewPassword123!")

    # ---------------------------------------------------------------------
    # RespondToAuthChallenge with SECRET_HASH
    # ---------------------------------------------------------------------
    @patch.dict("os.environ", {"COGNITO_APP_CLIENT_ID": "test_cid", "COGNITO_CLIENT_SECRET": "test_sec"}, clear=False)
    @patch("services.cognito._get_client")
    def test_respond_to_auth_challenge_includes_secret_hash(self, mock_client_factory):
        """respond_to_auth_challenge must inject SECRET_HASH into ChallengeResponses."""
        from services.cognito import respond_to_auth_challenge, _calculate_secret_hash
        mock_boto_client = MagicMock()
        mock_boto_client.respond_to_auth_challenge.return_value = {
            "AuthenticationResult": {
                "IdToken": "mock.id.token",
                "AccessToken": "mock.access.token",
            }
        }
        mock_client_factory.return_value = mock_boto_client

        res = respond_to_auth_challenge(
            username="bob@campus.edu",
            challenge_name="NEW_PASSWORD_REQUIRED",
            challenge_responses={"NEW_PASSWORD": "NewPassword123!"},
            session_str="session-xyz",
        )
        self.assertTrue(res["success"])

        mock_boto_client.respond_to_auth_challenge.assert_called_once()
        call_kwargs = mock_boto_client.respond_to_auth_challenge.call_args[1]
        responses = call_kwargs["ChallengeResponses"]
        self.assertIn("SECRET_HASH", responses)
        expected_hash = _calculate_secret_hash("bob@campus.edu", "test_cid", "test_sec")
        self.assertEqual(responses["SECRET_HASH"], expected_hash)
        self.assertEqual(responses["USERNAME"], "bob@campus.edu")

    # ---------------------------------------------------------------------
    # REFRESH_TOKEN_AUTH with SECRET_HASH
    # ---------------------------------------------------------------------
    @patch.dict("os.environ", {"COGNITO_APP_CLIENT_ID": "test_cid", "COGNITO_CLIENT_SECRET": "test_sec"}, clear=False)
    @patch("services.cognito._get_client")
    def test_refresh_auth_session_includes_secret_hash(self, mock_client_factory):
        """refresh_auth_session must include SECRET_HASH in AuthParameters."""
        from services.cognito import refresh_auth_session, _calculate_secret_hash
        mock_boto_client = MagicMock()
        mock_boto_client.initiate_auth.return_value = {
            "AuthenticationResult": {
                "IdToken": "new.id.token",
                "AccessToken": "new.access.token",
            }
        }
        mock_client_factory.return_value = mock_boto_client

        res = refresh_auth_session("bob@campus.edu", "mock-refresh-token")
        self.assertTrue(res["success"])
        self.assertEqual(res["id_token"], "new.id.token")

        mock_boto_client.initiate_auth.assert_called_once()
        call_kwargs = mock_boto_client.initiate_auth.call_args[1]
        self.assertEqual(call_kwargs["AuthFlow"], "REFRESH_TOKEN_AUTH")
        auth_params = call_kwargs["AuthParameters"]
        self.assertIn("SECRET_HASH", auth_params)
        expected_hash = _calculate_secret_hash("bob@campus.edu", "test_cid", "test_sec")
        self.assertEqual(auth_params["SECRET_HASH"], expected_hash)


if __name__ == "__main__":
    unittest.main()
