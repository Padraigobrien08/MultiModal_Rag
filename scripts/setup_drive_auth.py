#!/usr/bin/env python3
"""
One-time Google Drive OAuth setup.

Usage:
  python scripts/setup_drive_auth.py

Requirements:
  1. Create a project at https://console.cloud.google.com
  2. Enable the Google Drive API
  3. Create OAuth 2.0 credentials (Desktop app type)
  4. Download credentials JSON → save as data/drive_credentials.json

This script opens a browser for authorization and saves the token to
data/drive_token.json for use by sync_drive.py.
"""
import sys
from pathlib import Path

CREDENTIALS_PATH = Path("data/drive_credentials.json")
TOKEN_PATH = Path("data/drive_token.json")
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def main():
    if not CREDENTIALS_PATH.exists():
        print(f"""
ERROR: {CREDENTIALS_PATH} not found.

To set up Google Drive access:

1. Go to https://console.cloud.google.com
2. Create a new project (or select existing)
3. Enable the Google Drive API:
   APIs & Services → Enable APIs → search "Google Drive API" → Enable
4. Create OAuth credentials:
   APIs & Services → Credentials → Create Credentials → OAuth client ID
   Application type: Desktop app
   Name: Stepwise
5. Download the JSON file and save it as:
   data/drive_credentials.json

Then re-run this script.
""")
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            "Missing dependency. Run:\n"
            "  pip install google-auth-oauthlib google-api-python-client"
        )
        sys.exit(1)

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Opening browser for Google Drive authorization...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)

    TOKEN_PATH.write_text(creds.to_json())
    print(f"\n✓ Authorization complete. Token saved to {TOKEN_PATH}")
    print("\nYou can now run:")
    print("  python scripts/sync_drive.py --folder-id <your-folder-id>")
    print("\nTo find your folder ID: open the folder in Google Drive,")
    print("the ID is the last part of the URL:")
    print("  https://drive.google.com/drive/folders/THIS_IS_THE_FOLDER_ID")


if __name__ == "__main__":
    main()
