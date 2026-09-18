"""
services/cognito.py
-------------------
AWS Cognito user authentication helpers using boto3.

Provides:
  - register_user: Sign up a new user via Cognito User Pool
  - authenticate_user: Log in via USER_PASSWORD_AUTH flow
  - confirm_user: Confirm user registration with email verification code
  - is_cognito_configured: Check if Cognito environment variables are provided
"""

import os
import hmac
import hashlib
import base64
import json
import boto3
from botocore.exceptions import ClientError


def _get_client():
    """Return a boto3 Cognito IDP client configured from environment variables."""
    region = os.environ.get("AWS_REGION", "ap-south-1")
    return boto3.client("cognito-idp", region_name=region)


def is_cognito_configured() -> bool:
    """Return True if required Cognito environment variables are set."""
    return bool(os.environ.get("COGNITO_APP_CLIENT_ID"))


def _calculate_secret_hash(username: str, client_id: str, client_secret: str) -> str:
    """Compute HMAC-SHA256 secret hash required if App Client has a secret."""
    message = username + client_id
    dig = hmac.new(
        client_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(dig).decode()


def register_user(username: str, email: str, password: str) -> dict:
    """
    Register a new user in the Cognito User Pool.

    Returns:
        {"success": True, "user_confirmed": bool, "user_sub": str} on success
        {"success": False, "error": str} on failure
    """
    client_id = os.environ.get("COGNITO_APP_CLIENT_ID")
    if not client_id:
        return {
            "success": False,
            "error": "AWS Cognito is not configured. Please set COGNITO_APP_CLIENT_ID in .env.",
        }

    client = _get_client()
    client_secret = os.environ.get("COGNITO_CLIENT_SECRET")

    kwargs = {
        "ClientId": client_id,
        "Username": username,
        "Password": password,
        "UserAttributes": [
            {"Name": "email", "Value": email},
        ],
    }
    if client_secret:
        kwargs["SecretHash"] = _calculate_secret_hash(username, client_id, client_secret)

    try:
        response = client.sign_up(**kwargs)
        return {
            "success": True,
            "user_confirmed": response.get("UserConfirmed", False),
            "user_sub": response.get("UserSub", ""),
        }
    except ClientError as e:
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        return {"success": False, "error": error_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def authenticate_user(username: str, password: str) -> dict:
    """
    Authenticate an existing user via Cognito USER_PASSWORD_AUTH.

    Returns on success:
        {
          "success": True,
          "user": {
              "username": str,
              "email": str,
              "id_token": str,
              "access_token": str,
          }
        }
    Returns on failure:
        {"success": False, "error": str}
    """
    client_id = os.environ.get("COGNITO_APP_CLIENT_ID")
    if not client_id:
        return {
            "success": False,
            "error": "AWS Cognito is not configured. Please set COGNITO_APP_CLIENT_ID in .env.",
        }

    client = _get_client()
    client_secret = os.environ.get("COGNITO_CLIENT_SECRET")

    auth_params = {
        "USERNAME": username,
        "PASSWORD": password,
    }
    if client_secret:
        auth_params["SECRET_HASH"] = _calculate_secret_hash(username, client_id, client_secret)

    try:
        response = client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters=auth_params,
            ClientId=client_id,
        )

        # Check for authentication challenge (e.g. NEW_PASSWORD_REQUIRED)
        if "ChallengeName" in response:
            return {
                "success": False,
                "error": f"Additional authentication required: {response['ChallengeName']}",
            }

        result = response.get("AuthenticationResult", {})
        id_token = result.get("IdToken", "")
        access_token = result.get("AccessToken", "")

        # Extract email from ID Token JWT claims if available
        email = ""
        if id_token and "." in id_token:
            try:
                payload = id_token.split(".")[1]
                payload += "=" * (-len(payload) % 4)
                claims = json.loads(base64.b64decode(payload).decode("utf-8"))
                email = claims.get("email", "")
            except Exception:
                email = ""

        return {
            "success": True,
            "user": {
                "username": username,
                "email": email,
                "id_token": id_token,
                "access_token": access_token,
            },
        }
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        if error_code == "UserNotConfirmedException":
            return {
                "success": False,
                "error": "User account is not yet confirmed. Please verify your email first.",
            }
        elif error_code in ("NotAuthorizedException", "UserNotFoundException"):
            return {
                "success": False,
                "error": "Incorrect username or password.",
            }
        return {"success": False, "error": error_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def confirm_user(username: str, confirmation_code: str) -> dict:
    """Confirm user signup via email verification code."""
    client_id = os.environ.get("COGNITO_APP_CLIENT_ID")
    if not client_id:
        return {
            "success": False,
            "error": "AWS Cognito is not configured. Please set COGNITO_APP_CLIENT_ID in .env.",
        }

    client = _get_client()
    client_secret = os.environ.get("COGNITO_CLIENT_SECRET")

    kwargs = {
        "ClientId": client_id,
        "Username": username,
        "ConfirmationCode": confirmation_code,
    }
    if client_secret:
        kwargs["SecretHash"] = _calculate_secret_hash(username, client_id, client_secret)

    try:
        client.confirm_sign_up(**kwargs)
        return {"success": True}
    except ClientError as e:
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        return {"success": False, "error": error_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}
