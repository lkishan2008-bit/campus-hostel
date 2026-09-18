"""
services/cognito.py
-------------------
Helpers for AWS Cognito user authentication.

All functions below contain TODOs — fill them in once you have:
  - COGNITO_USER_POOL_ID
  - COGNITO_APP_CLIENT_ID
set in your .env file.

Cognito SDK used: boto3 (cognito-idp client)
"""

import os
import boto3
from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# Create the Cognito Identity Provider client
# ---------------------------------------------------------------------------
def _get_client():
    """
    Return a boto3 Cognito IDP client.

    TODO (Cognito): Ensure your AWS credentials are set either via:
      - Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
      - Or an IAM role attached to the EC2/Lambda running this code.
    """
    return boto3.client(
        "cognito-idp",
        region_name=os.environ.get("AWS_REGION", "ap-south-1"),
    )


# ---------------------------------------------------------------------------
# Sign up a new user
# ---------------------------------------------------------------------------
def register_user(username: str, email: str, password: str) -> dict:
    """
    Register a new user in the Cognito User Pool.

    Returns:
        {"success": True}  on success
        {"success": False, "error": "<message>"}  on failure

    TODO (Cognito): Uncomment and use the code below after setting env vars.
    """
    # TODO (Cognito): Implement registration.
    #
    # client = _get_client()
    # user_pool_client_id = os.environ["COGNITO_APP_CLIENT_ID"]
    # try:
    #     client.sign_up(
    #         ClientId=user_pool_client_id,
    #         Username=username,
    #         Password=password,
    #         UserAttributes=[
    #             {"Name": "email", "Value": email},
    #         ],
    #     )
    #     return {"success": True}
    # except ClientError as e:
    #     return {"success": False, "error": e.response["Error"]["Message"]}

    return {"success": False, "error": "Cognito not yet configured."}


# ---------------------------------------------------------------------------
# Authenticate (log in) an existing user
# ---------------------------------------------------------------------------
def authenticate_user(username: str, password: str) -> dict:
    """
    Authenticate a user with Cognito using the USER_PASSWORD_AUTH flow.

    Returns on success:
        {
          "success": True,
          "user": {
              "username":  <str>,
              "email":     <str>,
              "id_token":  <JWT str>,
          }
        }
    Returns on failure:
        {"success": False, "error": "<message>"}

    TODO (Cognito): Uncomment and use the code below after setting env vars.
      Also ensure the App Client does NOT require a secret (or handle HMAC).
    """
    # TODO (Cognito): Implement authentication.
    #
    # client = _get_client()
    # user_pool_client_id = os.environ["COGNITO_APP_CLIENT_ID"]
    # try:
    #     response = client.initiate_auth(
    #         AuthFlow="USER_PASSWORD_AUTH",
    #         AuthParameters={"USERNAME": username, "PASSWORD": password},
    #         ClientId=user_pool_client_id,
    #     )
    #     tokens = response["AuthenticationResult"]
    #     # Optionally decode the ID token to get email:
    #     # import base64, json
    #     # payload = tokens["IdToken"].split(".")[1]
    #     # payload += "=" * (-len(payload) % 4)
    #     # claims = json.loads(base64.b64decode(payload))
    #     return {
    #         "success": True,
    #         "user": {
    #             "username": username,
    #             "email":    claims.get("email", ""),
    #             "id_token": tokens["IdToken"],
    #         },
    #     }
    # except ClientError as e:
    #     return {"success": False, "error": e.response["Error"]["Message"]}

    return {"success": False, "error": "Cognito not yet configured."}


# ---------------------------------------------------------------------------
# Confirm a user's email (after sign-up verification code)
# ---------------------------------------------------------------------------
def confirm_user(username: str, confirmation_code: str) -> dict:
    """
    Confirm a new Cognito user with the verification code sent to their email.

    TODO (Cognito): Implement confirmation flow.
    """
    # client = _get_client()
    # user_pool_client_id = os.environ["COGNITO_APP_CLIENT_ID"]
    # try:
    #     client.confirm_sign_up(
    #         ClientId=user_pool_client_id,
    #         Username=username,
    #         ConfirmationCode=confirmation_code,
    #     )
    #     return {"success": True}
    # except ClientError as e:
    #     return {"success": False, "error": e.response["Error"]["Message"]}

    return {"success": False, "error": "Cognito not yet configured."}
