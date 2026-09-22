"""
services/cognito.py
-------------------
AWS Cognito user authentication helpers using boto3 with complete SECRET_HASH support.

Provides:
  - register_user: Sign up a new user via Cognito User Pool (SignUp)
  - authenticate_user: Log in via USER_PASSWORD_AUTH flow (InitiateAuth)
  - confirm_user: Confirm user registration with email verification code (ConfirmSignUp)
  - resend_verification_code: Re-send verification code (ResendConfirmationCode)
  - forgot_password: Initiate password recovery flow (ForgotPassword)
  - confirm_forgot_password: Confirm new password with code (ConfirmForgotPassword)
  - respond_to_auth_challenge: Respond to challenges with SECRET_HASH (RespondToAuthChallenge)
  - refresh_auth_session: Refresh tokens with SECRET_HASH (InitiateAuth REFRESH_TOKEN_AUTH)
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
    """
    Get the Cognito App Client secret securely from environment variables,
    cached value, or via describe_user_pool_client.
    Never hardcode or log client secrets.
    """
    global _CACHED_CLIENT_SECRET
    secret = os.environ.get("COGNITO_CLIENT_SECRET")
    if secret:
        return secret.strip()
    if _CACHED_CLIENT_SECRET:
        return _CACHED_CLIENT_SECRET

    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    cid = (client_id or os.environ.get("COGNITO_APP_CLIENT_ID") or "").strip()
    if user_pool_id and cid:
        try:
            client = _get_client()
            resp = client.describe_user_pool_client(
                UserPoolId=user_pool_id.strip(),
                ClientId=cid,
            )
            found_secret = resp.get("UserPoolClient", {}).get("ClientSecret")
            if found_secret:
                _CACHED_CLIENT_SECRET = found_secret.strip()
                return _CACHED_CLIENT_SECRET
        except Exception:
            pass

    return ""


def _calculate_secret_hash(username: str, client_id: str, client_secret: str) -> str:
    """
    Compute Base64(HMAC-SHA256(client_secret, username + client_id)).
    Required when the Cognito App Client has a secret configured.
    """
    if not (username and client_id and client_secret):
        return ""
    message = (str(username).strip() + str(client_id).strip()).encode("utf-8")
    key = str(client_secret).strip().encode("utf-8")
    dig = hmac.new(
        key,
        message,
        hashlib.sha256,
    ).digest()
    return base64.b64encode(dig).decode("utf-8")


def _extract_user_info(response: dict, default_username: str = "") -> dict:
    """Extract user claims and tokens from Cognito authentication response."""
    result = response.get("AuthenticationResult", {})
    id_token = result.get("IdToken", "")
    access_token = result.get("AccessToken", "")
    refresh_token = result.get("RefreshToken", "")

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

    clean_default = default_username.strip()
    fallback_display = clean_default.split("@")[0] if "@" in clean_default else clean_default
    final_username = preferred_name or (email.split("@")[0] if email else fallback_display)

    user_info = {
        "username": final_username,
        "email": email or (clean_default if "@" in clean_default else ""),
        "id_token": id_token,
        "access_token": access_token,
    }
    if refresh_token:
        user_info["refresh_token"] = refresh_token

    return {
        "success": True,
        "user": user_info,
    }


def register_user(username: str, email: str, password: str) -> dict:
    """
    Register a new user in the Cognito User Pool (SignUp).

    Returns:
        {"success": True, "user_confirmed": bool, "user_sub": str} on success
        {"success": False, "error": str} on failure
    """
    client_id = (os.environ.get("COGNITO_APP_CLIENT_ID") or "").strip()
    if not client_id:
        return {
            "success": False,
            "error": "AWS Cognito is not configured. Please set COGNITO_APP_CLIENT_ID in environment.",
        }

    client = _get_client()
    client_secret = _get_client_secret(client_id)

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
    Authenticate an existing user via Cognito USER_PASSWORD_AUTH (InitiateAuth).

    Returns on success:
        {
          "success": True,
          "user": {
              "username": str,
              "email": str,
              "id_token": str,
              "access_token": str,
              "refresh_token": str (optional)
          }
        }
    Returns on failure:
        {"success": False, "error": str}
    """
    client_id = (os.environ.get("COGNITO_APP_CLIENT_ID") or "").strip()
    if not client_id:
        return {
            "success": False,
            "error": "AWS Cognito is not configured. Please set COGNITO_APP_CLIENT_ID in environment.",
        }

    client = _get_client()
    client_secret = _get_client_secret(client_id)
    user_pool_id = (os.environ.get("COGNITO_USER_POOL_ID") or "").strip()

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

    try:
        response = client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters=auth_params,
            ClientId=client_id,
        )

        if "ChallengeName" in response:
            challenge = response.get("ChallengeName")
            session_str = response.get("Session")
            return {
                "success": False,
                "error": f"Additional authentication required: {challenge}",
                "challenge": challenge,
                "session": session_str,
                "username": cognito_username,
            }

        return _extract_user_info(response, default_username=cognito_username)

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        if error_code == "UserNotConfirmedException":
            return {
                "success": False,
                "error": "Your email is not verified yet. Please enter the verification code sent to your email.",
                "not_confirmed": True,
                "email": cognito_username,
            }
        elif error_code in ("NotAuthorizedException", "UserNotFoundException"):
            return {
                "success": False,
                "error": "Incorrect username or password.",
            }
        elif error_code == "PasswordResetRequiredException":
            return {
                "success": False,
                "error": "Password reset required. Please reset your password.",
                "password_reset_required": True,
                "email": cognito_username,
            }
        return {"success": False, "error": error_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def confirm_user(username: str, confirmation_code: str) -> dict:
    """
    Confirm user signup via email verification code (ConfirmSignUp).

    Returns:
        {"success": True} on success
        {"success": False, "error": str} on failure
    """
    client_id = (os.environ.get("COGNITO_APP_CLIENT_ID") or "").strip()
    if not client_id:
        return {
            "success": False,
            "error": "AWS Cognito is not configured. Please set COGNITO_APP_CLIENT_ID in environment.",
        }

    client = _get_client()
    client_secret = _get_client_secret(client_id)

    cognito_username = username.strip()
    kwargs = {
        "ClientId": client_id,
        "Username": cognito_username,
        "ConfirmationCode": str(confirmation_code).strip(),
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
        elif error_code == "UserNotFoundException":
            return {"success": False, "error": "No account found with this username or email."}
        return {"success": False, "error": error_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def resend_verification_code(username: str) -> dict:
    """
    Re-send the email verification code for an unconfirmed Cognito user (ResendConfirmationCode).

    Returns:
        {"success": True, "delivery_details": dict} on success
        {"success": False, "error": str} on failure
    """
    client_id = (os.environ.get("COGNITO_APP_CLIENT_ID") or "").strip()
    if not client_id:
        return {
            "success": False,
            "error": "AWS Cognito is not configured. Please set COGNITO_APP_CLIENT_ID in environment.",
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
        response = client.resend_confirmation_code(**kwargs)
        return {
            "success": True,
            "delivery_details": response.get("CodeDeliveryDetails", {}),
        }
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        if error_code == "UserNotFoundException":
            return {"success": False, "error": "No account found with this username or email."}
        elif error_code == "InvalidParameterException":
            return {"success": False, "error": "User is already confirmed or invalid request."}
        elif error_code == "LimitExceededException":
            return {"success": False, "error": "Attempt limit exceeded. Please try again later."}
        return {"success": False, "error": error_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def forgot_password(username: str) -> dict:
    """
    Initiate the forgot password flow for a Cognito user (ForgotPassword).

    Returns:
        {"success": True, "delivery_details": dict} on success
        {"success": False, "error": str} on failure
    """
    client_id = (os.environ.get("COGNITO_APP_CLIENT_ID") or "").strip()
    if not client_id:
        return {
            "success": False,
            "error": "AWS Cognito is not configured. Please set COGNITO_APP_CLIENT_ID in environment.",
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
        response = client.forgot_password(**kwargs)
        return {
            "success": True,
            "delivery_details": response.get("CodeDeliveryDetails", {}),
        }
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        if error_code == "UserNotFoundException":
            return {"success": False, "error": "No account found with that email or username."}
        elif error_code == "UserNotConfirmedException":
            return {"success": False, "error": "Account is not verified yet. Please verify your email first."}
        elif error_code == "LimitExceededException":
            return {"success": False, "error": "Attempt limit exceeded. Please try again later."}
        return {"success": False, "error": error_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def confirm_forgot_password(username: str, confirmation_code: str, new_password: str) -> dict:
    """
    Confirm a new password using the verification code received via forgot_password (ConfirmForgotPassword).

    Returns:
        {"success": True} on success
        {"success": False, "error": str} on failure
    """
    client_id = (os.environ.get("COGNITO_APP_CLIENT_ID") or "").strip()
    if not client_id:
        return {
            "success": False,
            "error": "AWS Cognito is not configured. Please set COGNITO_APP_CLIENT_ID in environment.",
        }

    client = _get_client()
    client_secret = _get_client_secret(client_id)

    cognito_username = username.strip()
    kwargs = {
        "ClientId": client_id,
        "Username": cognito_username,
        "ConfirmationCode": str(confirmation_code).strip(),
        "Password": new_password,
    }
    if client_secret:
        kwargs["SecretHash"] = _calculate_secret_hash(cognito_username, client_id, client_secret)

    try:
        client.confirm_forgot_password(**kwargs)
        return {"success": True}
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        if error_code == "CodeMismatchException":
            return {"success": False, "error": "Incorrect verification code. Please try again."}
        elif error_code == "ExpiredCodeException":
            return {"success": False, "error": "Verification code has expired. Please request a new one."}
        elif error_code == "InvalidPasswordException":
            return {"success": False, "error": f"Password requirement not met: {error_msg}"}
        elif error_code == "UserNotFoundException":
            return {"success": False, "error": "No account found with this username or email."}
        return {"success": False, "error": error_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def respond_to_auth_challenge(
    username: str,
    challenge_name: str,
    challenge_responses: dict,
    session_str: str = None,
) -> dict:
    """
    Respond to a Cognito auth challenge (RespondToAuthChallenge) including SECRET_HASH.

    Returns:
        {"success": True, "user": dict} or {"success": True, "challenge": str, "session": str}
        or {"success": False, "error": str}
    """
    client_id = (os.environ.get("COGNITO_APP_CLIENT_ID") or "").strip()
    if not client_id:
        return {
            "success": False,
            "error": "AWS Cognito is not configured. Please set COGNITO_APP_CLIENT_ID in environment.",
        }

    client = _get_client()
    client_secret = _get_client_secret(client_id)

    cognito_username = username.strip()
    responses = dict(challenge_responses or {})
    if "USERNAME" not in responses:
        responses["USERNAME"] = cognito_username
    if client_secret:
        target_user = responses.get("USERNAME", cognito_username)
        responses["SECRET_HASH"] = _calculate_secret_hash(target_user, client_id, client_secret)

    kwargs = {
        "ClientId": client_id,
        "ChallengeName": challenge_name,
        "ChallengeResponses": responses,
    }
    if session_str:
        kwargs["Session"] = session_str

    try:
        response = client.respond_to_auth_challenge(**kwargs)
        if "AuthenticationResult" in response:
            return _extract_user_info(response, default_username=cognito_username)
        return {
            "success": True,
            "challenge": response.get("ChallengeName"),
            "session": response.get("Session"),
        }
    except ClientError as e:
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        return {"success": False, "error": error_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def refresh_auth_session(username: str, refresh_token: str) -> dict:
    """
    Refresh authentication tokens via REFRESH_TOKEN_AUTH (InitiateAuth) including SECRET_HASH.

    Returns:
        {"success": True, "id_token": str, "access_token": str} on success
        {"success": False, "error": str} on failure
    """
    client_id = (os.environ.get("COGNITO_APP_CLIENT_ID") or "").strip()
    if not client_id:
        return {
            "success": False,
            "error": "AWS Cognito is not configured. Please set COGNITO_APP_CLIENT_ID in environment.",
        }

    client = _get_client()
    client_secret = _get_client_secret(client_id)

    cognito_username = username.strip()
    auth_params = {
        "REFRESH_TOKEN": refresh_token,
    }
    if client_secret and cognito_username:
        auth_params["SECRET_HASH"] = _calculate_secret_hash(cognito_username, client_id, client_secret)

    try:
        response = client.initiate_auth(
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters=auth_params,
            ClientId=client_id,
        )
        result = response.get("AuthenticationResult", {})
        return {
            "success": True,
            "id_token": result.get("IdToken", ""),
            "access_token": result.get("AccessToken", ""),
        }
    except ClientError as e:
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        return {"success": False, "error": error_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}
