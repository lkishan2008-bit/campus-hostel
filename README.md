# Campus Hostel Companion

A simple, clean web application for hostel students to view mess menus, raise complaints, and read announcements.

## Features
- **Sign Up / Log In** – Secure authentication via AWS Cognito
- **Mess Menu** – Today's hostel mess schedule at a glance
- **Raise Complaints** – Submit complaints with title, description, and category
- **Complaint History** – Track your own complaint statuses
- **Announcements** – Stay updated with hostel-wide notices

## Tech Stack
- **Frontend:** HTML, CSS, Vanilla JavaScript
- **Backend:** Python Flask
- **Auth:** AWS Cognito
- **Database:** AWS DynamoDB
- **Deployment:** AWS Amplify Hosting (planned)

## Local Setup

### 1. Clone & enter the project
```bash
git clone <repo-url>
cd campus-hostel
```

### 2. Create a virtual environment
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
```bash
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
```
Edit `.env` with your real AWS credentials and Cognito details.

### 5. Run the application
```bash
python app.py
```
Visit [http://localhost:5000](http://localhost:5000)

### Health Check
```
GET /health  →  {"status": "ok"}
```

## AWS Setup (Required before full functionality)
1. **Cognito** – Create a User Pool and App Client; copy the Pool ID and Client ID into `.env`
2. **DynamoDB** – Create 3 tables:
   - `campus-hostel-complaints` (Partition key: `complaint_id`)
   - `campus-hostel-announcements` (Partition key: `announcement_id`)
   - `campus-hostel-mess-menu` (Partition key: `day`)
3. **IAM** – Ensure your AWS credentials have read/write access to these DynamoDB tables

## Project Structure
```
campus-hostel/
├── app.py                  # Flask application entry point
├── requirements.txt
├── .env.example            # Template for environment variables
├── templates/              # Jinja2 HTML templates
│   ├── index.html          # Landing page
│   ├── dashboard.html      # Mess menu dashboard
│   ├── complaints.html     # Complaint history
│   ├── raise_complaint.html
│   └── announcements.html
├── static/
│   ├── css/style.css       # Global styles
│   └── js/app.js           # Client-side JavaScript
└── services/
    ├── dynamodb.py         # DynamoDB helpers (TODOs inside)
    └── cognito.py          # Cognito auth helpers (TODOs inside)
```
