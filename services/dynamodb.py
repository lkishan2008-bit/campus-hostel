"""
services/dynamodb.py
--------------------
AWS DynamoDB operations for Campus Hostel Companion:
  - get_todays_menu: Retrieve today's mess menu from the weekly schedule
  - get_weekly_menu: Retrieve the full 7-day weekly mess menu
  - save_weekly_menu: Write/overwrite the 7-day weekly mess menu
  - create_complaint: Insert a student complaint record
  - get_user_complaints: Retrieve complaints strictly for the authenticated user
  - get_announcements: Retrieve hostel-wide announcements (newest first)
"""

import os
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

FALLBACK_MENU = {
    "Monday":    {"breakfast": "Poha, Boiled Eggs, Tea & Coffee",       "lunch": "Steamed Rice, Dal Tadka, Sabzi, Roti, Curd",        "dinner": "Jeera Rice, Paneer Butter Masala, Tandoori Roti"},
    "Tuesday":   {"breakfast": "Idli, Sambar, Coconut Chutney, Tea",    "lunch": "Rajma Rice, Chapati, Salad, Papad",                "dinner": "Fried Rice, Mixed Veg Curry, Dal Fry, Roti"},
    "Wednesday": {"breakfast": "Upma, Boiled Eggs / Banana, Tea",       "lunch": "Chole Rice, Chapati, Raita, Salad",                "dinner": "Dal Makhani, Butter Naan, Steamed Rice, Kheer"},
    "Thursday":  {"breakfast": "Paratha, Curd, Pickle, Tea",            "lunch": "Steamed Rice, Sambhar, Rasam, Chapati, Papad",     "dinner": "Biryani, Raita, Mirchi ka Salan, Roti"},
    "Friday":    {"breakfast": "Bread Butter, Omelette / Jam, Tea",     "lunch": "Pulao, Kadai Paneer, Chapati, Salad",              "dinner": "Roti, Dal Tadka, Aloo Gobi, Rice, Gulab Jamun"},
    "Saturday":  {"breakfast": "Aloo Paratha, Curd, Pickle, Tea",       "lunch": "Pav Bhaji, Salad, Buttermilk",                    "dinner": "Paneer Tikka Masala, Jeera Rice, Roti, Ice Cream"},
    "Sunday":    {"breakfast": "Puri, Chole, Banana, Tea & Coffee",     "lunch": "Chicken Curry / Paneer Gravy, Rice, Roti, Raita", "dinner": "Special Biryani, Raita, Boondi Ladoo"},
}


def _get_resource():
    """Return a boto3 DynamoDB resource configured from environment variables."""
    region = os.environ.get("AWS_REGION", "ap-south-1")
    return boto3.resource("dynamodb", region_name=region)


def is_dynamodb_configured() -> bool:
    """Return True if AWS credentials or custom tables are set."""
    return bool(os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("DYNAMODB_COMPLAINTS_TABLE"))


# ---------------------------------------------------------------------------
# Mess Menu — Weekly
# ---------------------------------------------------------------------------
def get_weekly_menu() -> dict:
    """
    Fetch the complete 7-day mess menu from DynamoDB.
    Returns a dict keyed by day name, each value having breakfast/lunch/dinner.
    Falls back to FALLBACK_MENU if DynamoDB is unavailable or table is empty.
    """
    table_name = os.environ.get("DYNAMODB_MESS_MENU_TABLE", "campus-hostel-mess-menu")
    result = {}

    try:
        db = _get_resource()
        table = db.Table(table_name)
        for day in DAYS_OF_WEEK:
            response = table.get_item(Key={"day": day})
            item = response.get("Item")
            if item:
                result[day] = {
                    "breakfast": item.get("breakfast", ""),
                    "lunch":     item.get("lunch", ""),
                    "dinner":    item.get("dinner", ""),
                }
    except Exception:
        pass

    # Fill any missing days with fallback so the page never crashes
    for day in DAYS_OF_WEEK:
        if day not in result or not any(result[day].values()):
            result[day] = dict(FALLBACK_MENU[day])

    return result


def get_todays_menu() -> dict:
    """
    Fetch today's mess menu from the weekly schedule stored in DynamoDB.
    Returns a dict with day, breakfast, lunch, dinner.
    Falls back to the FALLBACK_MENU if DynamoDB is unavailable.
    """
    table_name = os.environ.get("DYNAMODB_MESS_MENU_TABLE", "campus-hostel-mess-menu")
    day_name = datetime.now().strftime("%A")

    try:
        db = _get_resource()
        table = db.Table(table_name)
        response = table.get_item(Key={"day": day_name})
        item = response.get("Item")
        if item and (item.get("breakfast") or item.get("lunch") or item.get("dinner")):
            return {
                "day":       item.get("day", day_name),
                "breakfast": item.get("breakfast", ""),
                "lunch":     item.get("lunch", ""),
                "dinner":    item.get("dinner", ""),
            }
    except Exception:
        pass

    fallback = FALLBACK_MENU.get(day_name, list(FALLBACK_MENU.values())[0])
    return {"day": day_name, **fallback}


def save_weekly_menu(menu_data: dict) -> tuple:
    """
    Write the 7-day weekly mess menu to DynamoDB.

    Args:
        menu_data: dict keyed by day name, each value must have
                   keys: breakfast, lunch, dinner  (all strings)

    Returns:
        (True, "") on success
        (False, error_message) on failure
    """
    table_name = os.environ.get("DYNAMODB_MESS_MENU_TABLE", "campus-hostel-mess-menu")

    try:
        db = _get_resource()
        table = db.Table(table_name)
        for day in DAYS_OF_WEEK:
            day_entry = menu_data.get(day, {})
            table.put_item(Item={
                "day":       day,
                "breakfast": str(day_entry.get("breakfast", "")).strip(),
                "lunch":     str(day_entry.get("lunch", "")).strip(),
                "dinner":    str(day_entry.get("dinner", "")).strip(),
            })
        return True, ""
    except ClientError as e:
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        return False, error_msg
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Complaints
# ---------------------------------------------------------------------------
def create_complaint(complaint: dict) -> tuple:
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
