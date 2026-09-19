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

_CACHED_CLIENT_SECRET = None


def _get_client():
    """Return a boto3 Cognito IDP client configured from environment variables."""
    region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "ap-south-1"))
    return boto3.client("cognito-idp", region_name=region)


def is_cognito_configured() -> bool:
    """Return True if required Cognito environment variables are set."""
    return bool(os.environ.get("COGNITO_APP_CLIENT_ID"))


def _get_client_secret(client_id: str = None) -> str:
    """Get the Cognito App Client secret from env, describe_user_pool_client, or cache."""
    global _CACHED_CLIENT_SECRET
    secret = os.environ.get("COGNITO_CLIENT_SECRET")
    if secret:
        return secret
    if _CACHED_CLIENT_SECRET:
        return _CACHED_CLIENT_SECRET

    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    cid = client_id or os.environ.get("COGNITO_APP_CLIENT_ID")
    if user_pool_id and cid:
        try:
            client = _get_client()
            resp = client.describe_user_pool_client(
                UserPoolId=user_pool_id,
                ClientId=cid,
            )
            found_secret = resp.get("UserPoolClient", {}).get("ClientSecret")
            if found_secret:
                _CACHED_CLIENT_SECRET = found_secret
                return _CACHED_CLIENT_SECRET
        except Exception:
            pass

    # Fallback to known client secret for this user pool app client if describe fails
    if cid == "500oqmag3r12jv4bpt2ng74alb":
        _CACHED_CLIENT_SECRET = "5j2npofsendjqe7gsrlnt9005jtac7htgb521nsmsa6tkm53kv2"
        return _CACHED_CLIENT_SECRET

    return ""


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
    client_secret = _get_client_secret(client_id)
    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID")

    email_clean = email.strip()
    cognito_username = email_clean if "@" in email_clean else username.strip()
    display_name = username.strip() or email_clean.split("@")[0]

    user_attrs = [{"Name": "email", "Value": email_clean}]
    if display_name:
        user_attrs.append({"Name": "name", "Value": display_name})
        user_attrs.append({"Name": "preferred_username", "Value": display_name})

    kwargs = {
        "ClientId": client_id,
        "Username": cognito_username,
        "Password": password,
        "UserAttributes": user_attrs,
    }
    if client_secret:
        kwargs["SecretHash"] = _calculate_secret_hash(cognito_username, client_id, client_secret)

    try:
        response = client.sign_up(**kwargs)
        user_confirmed = response.get("UserConfirmed", False)
        user_sub = response.get("UserSub", "")

        # Auto-confirm user so they can immediately log in with their password
        if user_pool_id and not user_confirmed:
            try:
                client.admin_confirm_sign_up(
                    UserPoolId=user_pool_id,
                    Username=cognito_username,
                )
                client.admin_update_user_attributes(
                    UserPoolId=user_pool_id,
                    Username=cognito_username,
                    UserAttributes=[{"Name": "email_verified", "Value": "true"}],
                )
                user_confirmed = True
            except Exception:
                pass

        return {
            "success": True,
            "user_confirmed": user_confirmed,
            "user_sub": user_sub,
        }
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        if error_code == "UsernameExistsException":
            return {"success": False, "error": "An account with this email/username already exists."}
        elif error_code == "InvalidPasswordException":
            return {"success": False, "error": f"Password requirement not met: {error_msg}"}
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
    client_secret = _get_client_secret(client_id)
    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID")

    cognito_username = username.strip()

    # If username doesn't have '@', check if we can resolve it to their email in Cognito
    if "@" not in cognito_username and user_pool_id:
        try:
            list_res = client.list_users(
                UserPoolId=user_pool_id,
                Filter=f'preferred_username = "{cognito_username}"',
            )
            users = list_res.get("Users", [])
            if not users:
                list_res = client.list_users(
                    UserPoolId=user_pool_id,
                    Filter=f'name = "{cognito_username}"',
                )
                users = list_res.get("Users", [])
            if users:
                for attr in users[0].get("Attributes", []):
                    if attr["Name"] == "email":
                        cognito_username = attr["Value"]
                        break
        except Exception:
            pass

    auth_params = {
        "USERNAME": cognito_username,
        "PASSWORD": password,
    }
    if client_secret:
        auth_params["SECRET_HASH"] = _calculate_secret_hash(cognito_username, client_id, client_secret)

    def _extract_user_info(response):
        result = response.get("AuthenticationResult", {})
        id_token = result.get("IdToken", "")
        access_token = result.get("AccessToken", "")

        email = ""
        preferred_name = ""
        if id_token and "." in id_token:
            try:
                payload = id_token.split(".")[1]
                payload += "=" * (-len(payload) % 4)
                claims = json.loads(base64.b64decode(payload).decode("utf-8"))
                email = claims.get("email", "")
                preferred_name = claims.get("name") or claims.get("preferred_username")
            except Exception:
                pass

        final_username = preferred_name or (email.split("@")[0] if email else username.strip())
        return {
            "success": True,
            "user": {
                "username": final_username,
                "email": email or (cognito_username if "@" in cognito_username else ""),
                "id_token": id_token,
                "access_token": access_token,
            },
        }

    try:
        response = client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters=auth_params,
            ClientId=client_id,
        )

        if "ChallengeName" in response:
            return {
                "success": False,
                "error": f"Additional authentication required: {response['ChallengeName']}",
            }

        return _extract_user_info(response)

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        if error_code == "UserNotConfirmedException":
            if user_pool_id:
                try:
                    # Auto-confirm and retry auth
                    client.admin_confirm_sign_up(UserPoolId=user_pool_id, Username=cognito_username)
                    client.admin_update_user_attributes(
                        UserPoolId=user_pool_id,
                        Username=cognito_username,
                        UserAttributes=[{"Name": "email_verified", "Value": "true"}],
                    )
                    retry_response = client.initiate_auth(
                        AuthFlow="USER_PASSWORD_AUTH",
                        AuthParameters=auth_params,
                        ClientId=client_id,
                    )
                    return _extract_user_info(retry_response)
                except Exception:
                    pass
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
    client_secret = _get_client_secret(client_id)

    cognito_username = username.strip()
    kwargs = {
        "ClientId": client_id,
        "Username": cognito_username,
        "ConfirmationCode": confirmation_code,
    }
    if client_secret:
        kwargs["SecretHash"] = _calculate_secret_hash(cognito_username, client_id, client_secret)

    try:
        client.confirm_sign_up(**kwargs)
        return {"success": True}
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        if error_code == "CodeMismatchException":
            return {"success": False, "error": "Incorrect verification code. Please try again."}
        elif error_code == "ExpiredCodeException":
            return {"success": False, "error": "Verification code has expired. Please request a new one."}
        elif error_code == "NotAuthorizedException":
            return {"success": False, "error": "This account is already confirmed. Please sign in."}
        return {"success": False, "error": error_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def resend_verification_code(username: str) -> dict:
    """Re-send the email verification code for an unconfirmed Cognito user."""
    client_id = os.environ.get("COGNITO_APP_CLIENT_ID")
    if not client_id:
        return {
            "success": False,
            "error": "AWS Cognito is not configured. Please set COGNITO_APP_CLIENT_ID in .env.",
        }

    client = _get_client()
    client_secret = _get_client_secret(client_id)

    cognito_username = username.strip()
    kwargs = {
        "ClientId": client_id,
        "Username": cognito_username,
    }
    if client_secret:
        kwargs["SecretHash"] = _calculate_secret_hash(cognito_username, client_id, client_secret)

    try:
        client.resend_confirmation_code(**kwargs)
        return {"success": True}
    except ClientError as e:
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        return {"success": False, "error": error_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}

