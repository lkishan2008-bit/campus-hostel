"""
services/dynamodb.py
--------------------
AWS DynamoDB operations for Campus Hostel Companion:
  - Mess Menu: get_todays_menu, get_weekly_menu, save_weekly_menu
  - Organizations: create_organization, get_organization, get_organization_by_invite_code
  - Membership: add_organization_member, get_user_membership, get_organization_members
  - Complaints: create_complaint, get_user_complaints, get_organization_complaints,
                get_complaint_by_id, update_complaint_status
  - Announcements: get_announcements
"""

import os
import uuid
import secrets
import string
from datetime import datetime, timezone
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
    region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "ap-south-1"))
    return boto3.resource("dynamodb", region_name=region)


def is_dynamodb_configured() -> bool:
    """Return True if AWS credentials or custom tables are set."""
    return bool(os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("DYNAMODB_COMPLAINTS_TABLE"))


# ---------------------------------------------------------------------------
# Mess Menu — Weekly & Daily
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
                   keys: breakfast, lunch, dinner (all strings)

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
# Organizations
# ---------------------------------------------------------------------------
def _generate_invite_code() -> str:
    """Generate a clean, unambiguous uppercase invite code like CH-8F2K."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    suffix = "".join(secrets.choice(alphabet) for _ in range(4))
    prefix = "".join(secrets.choice(alphabet) for _ in range(2))
    return f"{prefix}-{suffix}"


def create_organization(name: str, org_type: str, member_count: str, creator_id: str, phone: str = "") -> tuple:
    """
    Create a new organization/hostel in DynamoDB.

    Returns:
        (org_dict, "") on success
        (None, error_message) on failure
    """
    table_name = os.environ.get("DYNAMODB_ORGANIZATIONS_TABLE", "campus-hostel-organizations")
    org_id = f"org_{uuid.uuid4().hex[:12]}"
    invite_code = _generate_invite_code()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    org_item = {
        "organization_id": org_id,
        "organization_name": name.strip(),
        "organization_type": org_type.strip(),
        "member_count": str(member_count).strip(),
        "created_by": creator_id.strip(),
        "created_at": now_iso,
        "status": "active",
        "invite_code": invite_code,
        "warden_phone": phone.strip(),  # Stored securely server-side
    }

    try:
        db = _get_resource()
        table = db.Table(table_name)
        table.put_item(Item=org_item)
        return org_item, ""
    except ClientError as e:
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        return None, error_msg
    except Exception as e:
        return None, str(e)


def get_organization(organization_id: str) -> dict:
    """Retrieve an organization by ID."""
    if not organization_id:
        return None
    table_name = os.environ.get("DYNAMODB_ORGANIZATIONS_TABLE", "campus-hostel-organizations")

    try:
        db = _get_resource()
        table = db.Table(table_name)
        resp = table.get_item(Key={"organization_id": organization_id})
        return resp.get("Item")
    except Exception:
        return None


def get_organization_by_invite_code(invite_code: str) -> dict:
    """Find an organization by its secure invite/join code (case-insensitive)."""
    if not invite_code:
        return None
    table_name = os.environ.get("DYNAMODB_ORGANIZATIONS_TABLE", "campus-hostel-organizations")
    clean_code = invite_code.strip().upper()

    try:
        from boto3.dynamodb.conditions import Attr
        db = _get_resource()
        table = db.Table(table_name)

        # Scan with filter on invite_code
        resp = table.scan(FilterExpression=Attr("invite_code").eq(clean_code))
        items = resp.get("Items", [])
        if items:
            return items[0]
        # Fallback check for case-insensitive match if needed
        resp_all = table.scan()
        for item in resp_all.get("Items", []):
            if str(item.get("invite_code", "")).upper() == clean_code:
                return item
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Organization Memberships
# ---------------------------------------------------------------------------
def add_organization_member(organization_id: str, user_id: str, role: str = "student", user_name: str = "") -> tuple:
    """
    Record user membership in an organization with a specific role ('student' or 'warden').

    Returns:
        (True, "") on success
        (False, error_message) on failure
    """
    table_name = os.environ.get("DYNAMODB_MEMBERS_TABLE", "campus-hostel-organization-members")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    member_item = {
        "user_id": user_id.strip(),
        "organization_id": organization_id.strip(),
        "role": role.strip().lower(),
        "joined_at": now_iso,
        "status": "active",
        "user_name": user_name.strip() if user_name else user_id.strip(),
    }

    try:
        db = _get_resource()
        table = db.Table(table_name)
        table.put_item(Item=member_item)
        return True, ""
    except ClientError as e:
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        return False, error_msg
    except Exception as e:
        return False, str(e)


def get_user_membership(user_id: str) -> dict:
    """Retrieve the membership record for a given user."""
    if not user_id:
        return None
    table_name = os.environ.get("DYNAMODB_MEMBERS_TABLE", "campus-hostel-organization-members")

    try:
        db = _get_resource()
        table = db.Table(table_name)
        resp = table.get_item(Key={"user_id": user_id})
        item = resp.get("Item")
        if item:
            return item

        # If not found directly, scan as fallback
        from boto3.dynamodb.conditions import Attr
        resp = table.scan(FilterExpression=Attr("user_id").eq(user_id))
        items = resp.get("Items", [])
        return items[0] if items else None
    except Exception:
        return None


def get_organization_members(organization_id: str) -> list:
    """Retrieve all members of an organization."""
    if not organization_id:
        return []
    table_name = os.environ.get("DYNAMODB_MEMBERS_TABLE", "campus-hostel-organization-members")

    try:
        from boto3.dynamodb.conditions import Attr
        db = _get_resource()
        table = db.Table(table_name)
        resp = table.scan(FilterExpression=Attr("organization_id").eq(organization_id))
        return resp.get("Items", [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Complaints (Strict Isolation & Organization Scoping)
# ---------------------------------------------------------------------------
def create_complaint(complaint: dict) -> tuple:
    """
    Save a new complaint to DynamoDB.

    Required fields:
        complaint_id (str): UUID
        organization_id (str): Organization ID
        user_id (str): student username
        title (str): summary
        category (str): e.g. Maintenance, Water, Electricity
        description (str): full details
        status (str): "Submitted", "Pending", etc.
        created_at (str): ISO timestamp

    Optional fields:
        priority (str): Low, Medium, High, Critical
        ai_classification (dict): AI intelligence summary & suggestions
        updated_at (str): ISO timestamp
    """
    table_name = os.environ.get("DYNAMODB_COMPLAINTS_TABLE", "campus-hostel-complaints")

    # Set default status and timestamps if missing
    item = dict(complaint)
    if "status" not in item:
        item["status"] = "Submitted"
    if "created_at" not in item:
        item["created_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if "updated_at" not in item:
        item["updated_at"] = item["created_at"]

    try:
        db = _get_resource()
        table = db.Table(table_name)
        table.put_item(Item=item)
        return True, ""
    except ClientError as e:
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        return False, error_msg
    except Exception as e:
        return False, str(e)


def get_user_complaints(user_id: str, organization_id: str = None) -> list:
    """
    Fetch all complaints belonging strictly to the authenticated user.
    Enforces absolute user isolation so students cannot view another student's complaints.
    """
    if not user_id:
        return []

    table_name = os.environ.get("DYNAMODB_COMPLAINTS_TABLE", "campus-hostel-complaints")

    try:
        from boto3.dynamodb.conditions import Key, Attr
        db = _get_resource()
        table = db.Table(table_name)

        items = []
        try:
            # Query GSI if available
            response = table.query(
                IndexName="user_id-index",
                KeyConditionExpression=Key("user_id").eq(user_id),
            )
            items = response.get("Items", [])
        except Exception:
            # Scan fallback
            try:
                response = table.scan(
                    FilterExpression=Attr("user_id").eq(user_id)
                )
                items = response.get("Items", [])
            except Exception:
                items = []

        # Strict secondary defense: guarantee user_id matches
        filtered = [item for item in items if item.get("user_id") == user_id]

        # If organization_id is provided, also ensure organization match
        if organization_id:
            filtered = [item for item in filtered if not item.get("organization_id") or item.get("organization_id") == organization_id]

        filtered.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return filtered
    except Exception:
        return []


def get_organization_complaints(organization_id: str) -> list:
    """
    Fetch all complaints belonging to an organization.
    FOR AUTHORIZED WARDEN USE ONLY.
    """
    if not organization_id:
        return []

    table_name = os.environ.get("DYNAMODB_COMPLAINTS_TABLE", "campus-hostel-complaints")

    try:
        from boto3.dynamodb.conditions import Attr
        db = _get_resource()
        table = db.Table(table_name)

        # Filter by organization_id
        response = table.scan(
            FilterExpression=Attr("organization_id").eq(organization_id)
        )
        items = response.get("Items", [])
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items
    except Exception:
        return []


def get_complaint_by_id(complaint_id: str) -> dict:
    """Retrieve a single complaint record by complaint_id."""
    if not complaint_id:
        return None

    table_name = os.environ.get("DYNAMODB_COMPLAINTS_TABLE", "campus-hostel-complaints")

    try:
        db = _get_resource()
        table = db.Table(table_name)
        response = table.get_item(Key={"complaint_id": complaint_id})
        item = response.get("Item")
        if item:
            return item

        # Scan fallback
        from boto3.dynamodb.conditions import Attr
        response = table.scan(FilterExpression=Attr("complaint_id").eq(complaint_id))
        items = response.get("Items", [])
        return items[0] if items else None
    except Exception:
        return None


def update_complaint_status(complaint_id: str, new_status: str, organization_id: str = None) -> tuple:
    """
    Update the status of a complaint.

    Args:
        complaint_id: UUID of complaint
        new_status: "Submitted", "Under Review", "In Progress", "Resolved", "Rejected"
        organization_id: If provided, verifies the complaint belongs to this organization.

    Returns:
        (True, "") on success
        (False, error_msg) on failure
    """
    if not complaint_id or not new_status:
        return False, "Complaint ID and status are required."

    table_name = os.environ.get("DYNAMODB_COMPLAINTS_TABLE", "campus-hostel-complaints")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        db = _get_resource()
        table = db.Table(table_name)

        # Retrieve existing item to verify organization scoping
        existing = get_complaint_by_id(complaint_id)
        if not existing:
            return False, "Complaint not found."

        if organization_id and existing.get("organization_id") and existing.get("organization_id") != organization_id:
            return False, "Unauthorized: Complaint belongs to a different organization."

        table.update_item(
            Key={"complaint_id": complaint_id},
            UpdateExpression="SET #st = :status, updated_at = :updated_at",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":status": new_status,
                ":updated_at": now_iso,
            },
        )
        return True, ""
    except ClientError as e:
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        return False, error_msg
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------------
def get_announcements(organization_id: str = None) -> list:
    """
    Fetch all announcements from DynamoDB, sorted newest first.
    If organization_id is provided, includes hostel-wide announcements or org-specific ones.
    """
    table_name = os.environ.get("DYNAMODB_ANNOUNCEMENTS_TABLE", "campus-hostel-announcements")

    try:
        db = _get_resource()
        table = db.Table(table_name)
        response = table.scan()
        items = response.get("Items", [])
        if organization_id:
            items = [item for item in items if not item.get("organization_id") or item.get("organization_id") == organization_id]
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items
    except Exception:
        return []
