"""
services/whatsapp.py
--------------------
WhatsApp Cloud API notification service for Campus Hostel Companion.

When a student raises a complaint, this service sends a minimal notification
to the authorized warden/guardian.

Security & Resilience:
  - All credentials are read from server-side environment variables.
  - No secrets or tokens are exposed to frontend or logged.
  - If WhatsApp is not configured or fails, the application continues
    working normally without breaking complaint creation.
"""

import os
import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


def is_whatsapp_configured() -> bool:
    """Return True if required WhatsApp Cloud API variables are set."""
    enabled = os.environ.get("WHATSAPP_ENABLED", "false").lower() in ("true", "1", "yes")
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    return bool(enabled and token and phone_id)


def send_warden_complaint_notification(complaint: dict, recipient_phone: str = None) -> bool:
    """
    Send a WhatsApp notification to the warden regarding a new complaint.

    Args:
        complaint: Dict containing 'category', 'priority', 'complaint_id', etc.
        recipient_phone: Warden's phone number. If None, falls back to env var WARDEN_PHONE_NUMBER.

    Returns:
        bool: True if sent successfully, False otherwise.
    """
    if not is_whatsapp_configured():
        logger.info("WhatsApp notification skipped/not configured.")
        return False

    token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    api_version = os.environ.get("WHATSAPP_API_VERSION", "v19.0").strip()

    target_phone = recipient_phone or os.environ.get("WARDEN_PHONE_NUMBER", "").strip()
    if not target_phone:
        logger.info("WhatsApp notification skipped: No warden phone number available.")
        return False

    # Format phone: remove spaces, dashes, parentheses
    clean_phone = "".join(ch for ch in target_phone if ch.isdigit() or ch == "+")
    if clean_phone.startswith("+"):
        clean_phone = clean_phone[1:]

    category = complaint.get("category", "General")
    priority = complaint.get("priority", "Medium")

    # Construct minimal, non-sensitive notification message
    message_text = (
        "New hostel complaint received.\n"
        f"Category: {category}\n"
        f"Priority: {priority}\n"
        "Please open the Warden Dashboard to review."
    )

    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_phone,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message_text,
        },
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status in (200, 201):
                logger.info("WhatsApp notification delivered successfully.")
                return True
            else:
                logger.warning("WhatsApp notification responded with status %s", resp.status)
                return False
    except Exception as e:
        # Safe log without token
        logger.warning("WhatsApp notification could not be sent: %s", str(e))
        return False
