"""
services/dynamodb.py
--------------------
AWS DynamoDB operations for Campus Hostel Companion:
  - get_todays_menu: Retrieve today's mess menu
  - create_complaint: Insert a student complaint record
  - get_user_complaints: Retrieve complaints strictly for the authenticated user
  - get_announcements: Retrieve hostel-wide announcements (newest first)
"""

import os
from datetime import datetime
import boto3
from botocore.exceptions import ClientError


def _get_resource():
    """Return a boto3 DynamoDB resource configured from environment variables."""
    region = os.environ.get("AWS_REGION", "ap-south-1")
    return boto3.resource("dynamodb", region_name=region)


def is_dynamodb_configured() -> bool:
    """Return True if AWS credentials or custom tables are set."""
    return bool(os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("DYNAMODB_COMPLAINTS_TABLE"))


# ---------------------------------------------------------------------------
# Mess Menu
# ---------------------------------------------------------------------------
def get_todays_menu() -> dict:
    """
    Fetch today's mess menu from DynamoDB for the current day of the week.
    Returns a dict with breakfast, lunch, snacks, dinner, and day.
    """
    table_name = os.environ.get("DYNAMODB_MESS_MENU_TABLE", "campus-hostel-mess-menu")
    day_name = datetime.now().strftime("%A")

    try:
        db = _get_resource()
        table = db.Table(table_name)
        response = table.get_item(Key={"day": day_name})
        item = response.get("Item")
        if item:
            return item
    except Exception:
        pass

    # Standard fallback schedule if table is not yet seeded
    return {
        "day": day_name,
        "breakfast": "Poha, Boiled Eggs / Banana, Tea & Coffee",
        "lunch": "Steamed Rice, Dal Tadka, Seasonal Sabzi, Chapati, Curd, Salad",
        "snacks": "Veg Cutlet / Samosa, Masala Chai",
        "dinner": "Jeera Rice, Paneer Butter Masala / Dal Makhani, Tandoori Roti, Kheer",
    }


# ---------------------------------------------------------------------------
# Complaints
# ---------------------------------------------------------------------------
def create_complaint(complaint: dict) -> tuple[bool, str]:
    """
    Save a new complaint to DynamoDB.

    Required fields in complaint dict:
        complaint_id (str): UUID
        user_id (str): student username
        title (str): summary
        category (str): e.g. Maintenance, Food, Cleanliness
        description (str): full details
        status (str): "Pending" or "Open"
        created_at (str): ISO 8601 timestamp

    Returns:
        (True, "") on success
        (False, error_message) on failure
    """
    table_name = os.environ.get("DYNAMODB_COMPLAINTS_TABLE", "campus-hostel-complaints")

    try:
        db = _get_resource()
        table = db.Table(table_name)
        table.put_item(Item=complaint)
        return True, ""
    except ClientError as e:
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        return False, error_msg
    except Exception as e:
        return False, str(e)


def get_user_complaints(user_id: str) -> list:
    """
    Fetch all complaints belonging strictly to the authenticated user.
    Enforces user isolation so students cannot view another student's complaints.
    """
    if not user_id:
        return []

    table_name = os.environ.get("DYNAMODB_COMPLAINTS_TABLE", "campus-hostel-complaints")

    try:
        from boto3.dynamodb.conditions import Key, Attr
        db = _get_resource()
        table = db.Table(table_name)

        items = []
        # Try GSI query on user_id-index first
        try:
            response = table.query(
                IndexName="user_id-index",
                KeyConditionExpression=Key("user_id").eq(user_id),
            )
            items = response.get("Items", [])
        except Exception:
            # Fallback to filtered scan if GSI is not indexed or unavailable
            try:
                response = table.scan(
                    FilterExpression=Attr("user_id").eq(user_id)
                )
                items = response.get("Items", [])
            except Exception:
                items = []

        # Secondary defense: strictly ensure every item matches user_id
        filtered = [item for item in items if item.get("user_id") == user_id]
        filtered.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return filtered
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------------
def get_announcements() -> list:
    """
    Fetch all announcements from DynamoDB, sorted newest first.
    """
    table_name = os.environ.get("DYNAMODB_ANNOUNCEMENTS_TABLE", "campus-hostel-announcements")

    try:
        db = _get_resource()
        table = db.Table(table_name)
        response = table.scan()
        items = response.get("Items", [])
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items
    except Exception:
        return []
