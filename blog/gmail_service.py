import os
import base64
from email.mime.text import MIMEText
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


BASE_DIR = Path(__file__).resolve().parent.parent

TOKEN_FILE = BASE_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


def send_gmail(to_email, subject, body):
    creds = Credentials.from_authorized_user_file(
        str(TOKEN_FILE),
        SCOPES
    )

    # Refresh expired access token
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

        # Save refreshed token
        TOKEN_FILE.write_text(
            creds.to_json(),
            encoding="utf-8"
        )

    service = build(
        "gmail",
        "v1",
        credentials=creds
    )

    message = MIMEText(body)

    message["to"] = to_email
    message["from"] = os.getenv(
        "GMAIL_FROM_EMAIL",
        "codelearnhub.in@gmail.com"
    )
    message["subject"] = subject

    encoded_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode()

    service.users().messages().send(
        userId="me",
        body={
            "raw": encoded_message
        }
    ).execute()

    print(f"Email sent successfully to {to_email}")