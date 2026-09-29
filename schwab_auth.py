import json
import os
import datetime
import base64
import logging
from cryptography.fernet import Fernet

import firestore_db
from schwab_api import schwab_request


class SchwabAuthManager:
    # Proactively refresh the access token this many seconds before it expires.
    EXPIRATION_BUFFER_SECONDS = 300

    def __init__(self):
        # Encryption key for securing tokens at rest in Firestore
        self.key = os.environ.get("SCHWAB_ENCRYPTION_KEY")
        if not self.key:
            raise ValueError(
                "SCHWAB_ENCRYPTION_KEY must be set in production to prevent token data loss."
            )

        self.fernet = Fernet(self.key.encode() if isinstance(self.key, str) else self.key)
        self.client_id = os.environ.get("SCHWAB_CLIENT_ID")
        self.client_secret = os.environ.get("SCHWAB_CLIENT_SECRET")
        self.redirect_uri = os.environ.get("SCHWAB_REDIRECT_URI")

    def _encrypt_tokens(self, tokens: dict) -> str:
        """Encrypts token dictionary using AES-256 Fernet encryption."""
        serialized = json.dumps(tokens)
        encrypted = self.fernet.encrypt(serialized.encode())
        return encrypted.decode()

    def _decrypt_tokens(self, encrypted_str: str) -> dict:
        """Decrypts token string back into a dictionary."""
        decrypted = self.fernet.decrypt(encrypted_str.encode())
        return json.loads(decrypted.decode())

    def save_user_tokens(self, uid: str, tokens: dict) -> None:
        """Encrypts and saves Schwab tokens to the user's Firestore document."""
        if "retrieved_at" not in tokens:
            tokens["retrieved_at"] = datetime.datetime.now().isoformat()

        encrypted_data = self._encrypt_tokens(tokens)
        firestore_db.save_user_schwab_credentials(uid, encrypted_data)

    def get_user_tokens(self, uid: str) -> dict | None:
        """Retrieves and decrypts the Schwab tokens for the user."""
        encrypted_data = firestore_db.get_user_schwab_credentials(uid)
        if not encrypted_data:
            return None

        try:
            return self._decrypt_tokens(encrypted_data)
        except Exception as e:
            logging.error("Failed to decrypt Schwab tokens for user %s: %s", uid, e)
            return None

    def disconnect_user(self, uid: str) -> None:
        """Removes the Schwab credentials from the user's Firestore document."""
        firestore_db.delete_user_schwab_credentials(uid)

    def _is_access_token_expired(self, tokens: dict) -> bool:
        """Checks if the access token is close to expiration (with 5-minute buffer)."""
        if "retrieved_at" not in tokens or "expires_in" not in tokens:
            return True
        retrieved_time = datetime.datetime.fromisoformat(tokens["retrieved_at"])
        expiration_threshold = retrieved_time + datetime.timedelta(
            seconds=tokens["expires_in"] - self.EXPIRATION_BUFFER_SECONDS
        )
        return datetime.datetime.now() >= expiration_threshold

    def _make_token_request(self, payload: dict) -> dict | None:
        """Helper to make a POST request to Schwab token endpoint."""
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            return schwab_request(
                "POST",
                "https://api.schwabapi.com/v1/oauth/token",
                headers=headers,
                data=payload,
            )
        except Exception as e:
            logging.error("Error during Schwab token request: %s", e)
            if hasattr(e, "response") and e.response is not None:
                logging.error(
                    "Response status: %s, body: %s", e.response.status_code, e.response.text
                )
            return None

    def refresh_user_tokens_if_needed(self, uid: str) -> str | None:
        """Retrieves user tokens, checks expiration, refreshes if needed, and returns a valid access token."""
        tokens = self.get_user_tokens(uid)
        if not tokens:
            return None

        if not self._is_access_token_expired(tokens):
            return tokens.get("access_token")

        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            logging.warning("No refresh token available for user %s", uid)
            return None

        logging.info("Refreshing Schwab access token for user %s...", uid)
        payload = {"grant_type": "refresh_token", "refresh_token": refresh_token}

        new_tokens = self._make_token_request(payload)
        if not new_tokens:
            return None

        # Schwab's refresh token may or may not rotate. Keep the existing one if not returned.
        if "refresh_token" not in new_tokens:
            new_tokens["refresh_token"] = refresh_token

        new_tokens["retrieved_at"] = datetime.datetime.now().isoformat()
        self.save_user_tokens(uid, new_tokens)
        return new_tokens.get("access_token")

    def exchange_code_for_tokens(self, auth_code: str) -> dict | None:
        """Exchanges an authorization code for access and refresh tokens."""
        if not self.client_id or not self.client_secret or not self.redirect_uri:
            logging.error(
                "Schwab CLIENT_ID, CLIENT_SECRET, or REDIRECT_URI "
                "environment variables are missing."
            )
            return None

        payload = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": self.redirect_uri,
        }

        tokens = self._make_token_request(payload)
        if not tokens:
            return None

        tokens["retrieved_at"] = datetime.datetime.now().isoformat()
        return tokens
