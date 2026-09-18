"""
services/dynamodb.py
--------------------
Helpers for AWS DynamoDB operations.

Tables expected (create these in AWS before connecting):
  1. campus-hostel-complaints     — PK: complaint_id (S)
  2. campus-hostel-announcements  — PK: announcement_id (S)
  3. campus-hostel-mess-menu      — PK: day (S)  e.g., "Monday", "Tuesday"

All functions below contain TODOs — fill them in once the DynamoDB tables exist
and your AWS credentials are set in .env.
"""

import os
import boto3
from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# Create the DynamoDB resource
# ---------------------------------------------------------------------------
def _get_resource():
    """
    Return a boto3 DynamoDB resource.

    TODO (DynamoDB): Ensure your AWS credentials are set either via:
      - Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
      - Or an IAM role attached to the compute resource.
    """
    return boto3.resource(
        "dynamodb",
        region_name=os.environ.get("AWS_REGION", "ap-south-1"),
    )


# ---------------------------------------------------------------------------
# Mess Menu
# ---------------------------------------------------------------------------
def get_todays_menu() -> dict:
    """
    Fetch today's mess menu from DynamoDB.

    Returns a dict like:
        {"breakfast": "...", "lunch": "...", "snacks": "...", "dinner": "..."}
    Returns an empty dict if no menu found.

    TODO (DynamoDB): Uncomment the code below after creating the table.
    """
    # import datetime
    # day_name = datetime.datetime.now().strftime("%A")   # e.g., "Monday"
    # try:
    #     db = _get_resource()
    #     table = db.Table(os.environ["DYNAMODB_MESS_MENU_TABLE"])
    #     response = table.get_item(Key={"day": day_name})
    #     return response.get("Item", {})
    # except ClientError as e:
    #     print("DynamoDB error (get_todays_menu):", e)
    #     return {}

    return {}  # Returns empty dict until DynamoDB is connected


# ---------------------------------------------------------------------------
# Complaints
# ---------------------------------------------------------------------------
def create_complaint(complaint: dict) -> bool:
    """
    Save a new complaint to DynamoDB.

    Args:
        complaint: dict with keys:
            complaint_id, user_id, title, category, description,
            status, created_at

    Returns True on success, False on failure.

    TODO (DynamoDB): Uncomment the code below after creating the table.
    """
    # try:
    #     db = _get_resource()
    #     table = db.Table(os.environ["DYNAMODB_COMPLAINTS_TABLE"])
    #     table.put_item(Item=complaint)
    #     return True
    # except ClientError as e:
    #     print("DynamoDB error (create_complaint):", e)
    #     return False

    return False  # Returns False until DynamoDB is connected


def get_user_complaints(user_id: str) -> list:
    """
    Fetch all complaints belonging to a specific user.

    Returns a list of complaint dicts, newest first.

    TODO (DynamoDB): Uncomment the code below after creating the table.
      Also create a Global Secondary Index (GSI) on user_id for efficient queries:
        GSI name: user_id-index   PK: user_id (S)

    Without a GSI, you'd need a full scan (not recommended for production).
    """
    # try:
    #     from boto3.dynamodb.conditions import Key
    #     db = _get_resource()
    #     table = db.Table(os.environ["DYNAMODB_COMPLAINTS_TABLE"])
    #     response = table.query(
    #         IndexName="user_id-index",
    #         KeyConditionExpression=Key("user_id").eq(user_id),
    #     )
    #     items = response.get("Items", [])
    #     # Sort newest first by created_at
    #     items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    #     return items
    # except ClientError as e:
    #     print("DynamoDB error (get_user_complaints):", e)
    #     return []

    return []  # Returns empty list until DynamoDB is connected


# ---------------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------------
def get_announcements() -> list:
    """
    Fetch all announcements from DynamoDB, sorted newest first.

    Returns a list of announcement dicts.

    TODO (DynamoDB): Uncomment the code below after creating the table.
      For production, add a sort key or use a scan with a filter.
    """
    # try:
    #     db = _get_resource()
    #     table = db.Table(os.environ["DYNAMODB_ANNOUNCEMENTS_TABLE"])
    #     response = table.scan()
    #     items = response.get("Items", [])
    #     items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    #     return items
    # except ClientError as e:
    #     print("DynamoDB error (get_announcements):", e)
    #     return []

    return []  # Returns empty list until DynamoDB is connected
