"""
test_suite.py
--------------
Automated testing for Campus Hostel Companion 5 core functions:
  1. Test signup (Cognito register)
  2. Test login (Cognito auth + session)
  3. Test logout (Session clear)
  4. Test authenticated dashboard (Mess menu + quick actions)
  5. Test creating a complaint (DynamoDB save with title, category, description, status, timestamp)
  6. Test viewing complaint history
  7. Test announcement loading
  8. Test user complaint isolation (Student A cannot see Student B's private complaints)
  9. Test health endpoint
"""

import unittest
from unittest.mock import patch, MagicMock
from app import app


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
    @patch("app.authenticate_user")
    def test_login_success(self, mock_auth):
        """Test successful authentication sets session and redirects to dashboard."""
        mock_auth.return_value = {
            "success": True,
            "user": {
                "username": "student_alice",
                "email": "alice@campus.edu",
                "id_token": "mock-id-token",
                "access_token": "mock-access-token",
            },
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
            "snacks": "Poha & Tea",
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
    @patch("app.create_complaint")
    def test_raise_complaint_success(self, mock_create):
        """Test submitting a complaint creates a DynamoDB record."""
        mock_create.return_value = (True, "")

        with self.client.session_transaction() as sess:
            sess["user"] = {"username": "student_alice"}

        resp = self.client.post("/raise-complaint", data={
            "title": "Leaking tap in Room 302",
            "category": "Water Supply",
            "description": "Bathroom tap is dripping continuously.",
        }, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/complaints"))

        # Check complaint record passed to create_complaint
        mock_create.assert_called_once()
        record = mock_create.call_args[0][0]
        self.assertEqual(record["user_id"], "student_alice")
        self.assertEqual(record["title"], "Leaking tap in Room 302")
        self.assertEqual(record["category"], "Water Supply")
        self.assertEqual(record["description"], "Bathroom tap is dripping continuously.")
        self.assertEqual(record["status"], "Pending")
        self.assertTrue("complaint_id" in record)
        self.assertTrue("created_at" in record)

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
                "category": "Internet / WiFi",
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
        self.assertIn(b"Internet / WiFi", resp.data)

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
            # Simulate GSI query raising error and falling back to filtered scan
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


if __name__ == "__main__":
    unittest.main()
