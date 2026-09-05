"""Gmail API integration via google-api-python-client."""
import asyncio
import base64
import logging
from email.mime.text import MIMEText
from pathlib import Path

from jarvis.config import settings

logger = logging.getLogger("jarvis.tools.gmail")

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_DISABLED_MSG = "Gmail integration is disabled. Set GMAIL_ENABLED=true to enable."


def _get_credentials():
    """Load or refresh OAuth credentials, re-authing if gmail scopes are missing."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = Path(settings.GOOGLE_TOKEN_FILE)
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path))
        # Re-auth if the stored token lacks gmail scopes
        if creds and not set(SCOPES).issubset(set(creds.scopes or [])):
            creds = None

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        creds_file = settings.GOOGLE_CREDENTIALS_FILE
        if not Path(creds_file).exists():
            raise FileNotFoundError(
                f"Google credentials file not found: {creds_file}"
            )
        # Combine gmail scopes with any existing calendar scopes
        all_scopes = list(set(SCOPES))
        if token_path.exists():
            try:
                old = Credentials.from_authorized_user_file(str(token_path))
                if old.scopes:
                    all_scopes = list(set(all_scopes) | set(old.scopes))
            except Exception:
                pass
        flow = InstalledAppFlow.from_client_secrets_file(creds_file, all_scopes)
        creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return creds


def _build_service():
    """Build and return a Gmail API service instance."""
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=_get_credentials())


def _decode_body(payload: dict) -> str:
    """Extract text/plain body from a message payload, handling multipart."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        result = _decode_body(part)
        if result:
            return result
    return ""


async def _run_sync(func, *args):
    """Run a blocking function in the default executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


async def gmail_get_inbox(count: int = 10) -> str:
    """Get recent inbox messages with sender, subject, snippet, and date."""
    if not settings.GMAIL_ENABLED:
        return _DISABLED_MSG
    count = max(1, min(count, 50))
    try:
        service = await _run_sync(_build_service)
        results = await _run_sync(
            lambda: service.users().messages().list(
                userId="me", labelIds=["INBOX"], maxResults=count
            ).execute()
        )
        messages = results.get("messages", [])
        if not messages:
            return "Inbox is empty."

        lines = []
        for msg_meta in messages:
            msg = await _run_sync(
                lambda mid=msg_meta["id"]: service.users().messages().get(
                    userId="me", id=mid, format="metadata",
                    metadataHeaders=["From", "Subject", "Date"]
                ).execute()
            )
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            lines.append(
                f"ID: {msg['id']} | From: {headers.get('From', '?')} | "
                f"Subject: {headers.get('Subject', '(no subject)')} | "
                f"Date: {headers.get('Date', '?')} | "
                f"Snippet: {msg.get('snippet', '')}"
            )
        return f"Inbox ({len(lines)} messages):\n" + "\n".join(lines)
    except Exception as e:
        logger.exception("gmail_get_inbox failed")
        return f"Error reading inbox: {e}"


async def gmail_get_unread_count() -> str:
    """Count unread messages in the inbox."""
    if not settings.GMAIL_ENABLED:
        return _DISABLED_MSG
    try:
        service = await _run_sync(_build_service)
        results = await _run_sync(
            lambda: service.users().messages().list(
                userId="me", labelIds=["INBOX", "UNREAD"], maxResults=1
            ).execute()
        )
        total = results.get("resultSizeEstimate", 0)
        if total == 0:
            return "No unread emails. Inbox zero!"
        return f"You have {total} unread email(s)."
    except Exception as e:
        logger.exception("gmail_get_unread_count failed")
        return f"Error checking unread count: {e}"


async def gmail_read_email(message_id: str) -> str:
    """Read the full content of an email by message ID."""
    if not settings.GMAIL_ENABLED:
        return _DISABLED_MSG
    try:
        service = await _run_sync(_build_service)
        msg = await _run_sync(
            lambda: service.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()
        )
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = _decode_body(msg.get("payload", {})) or "(no text content)"
        if len(body) > 5000:
            body = body[:5000] + "... (truncated)"
        return (
            f"From: {headers.get('From', '?')}\n"
            f"To: {headers.get('To', '?')}\n"
            f"Date: {headers.get('Date', '?')}\n"
            f"Subject: {headers.get('Subject', '(no subject)')}\n\n"
            f"{body}"
        )
    except Exception as e:
        logger.exception("gmail_read_email failed")
        return f"Error reading email: {e}"


async def gmail_search(query: str, count: int = 10) -> str:
    """Search emails using Gmail query syntax."""
    if not settings.GMAIL_ENABLED:
        return _DISABLED_MSG
    count = max(1, min(count, 50))
    try:
        service = await _run_sync(_build_service)
        results = await _run_sync(
            lambda: service.users().messages().list(
                userId="me", q=query, maxResults=count
            ).execute()
        )
        messages = results.get("messages", [])
        if not messages:
            return f"No emails matching '{query}'."

        lines = []
        for msg_meta in messages:
            msg = await _run_sync(
                lambda mid=msg_meta["id"]: service.users().messages().get(
                    userId="me", id=mid, format="metadata",
                    metadataHeaders=["From", "Subject", "Date"]
                ).execute()
            )
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            lines.append(
                f"ID: {msg['id']} | From: {headers.get('From', '?')} | "
                f"Subject: {headers.get('Subject', '(no subject)')} | "
                f"Date: {headers.get('Date', '?')} | "
                f"Snippet: {msg.get('snippet', '')}"
            )
        return f"Search results for '{query}' ({len(lines)} messages):\n" + "\n".join(lines)
    except Exception as e:
        logger.exception("gmail_search failed")
        return f"Error searching emails: {e}"


async def gmail_send_draft(to: str, subject: str, body: str) -> str:
    """Create a draft email (never sends). Returns draft ID for review."""
    if not settings.GMAIL_ENABLED:
        return _DISABLED_MSG
    try:
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

        service = await _run_sync(_build_service)
        draft = await _run_sync(
            lambda: service.users().drafts().create(
                userId="me", body={"message": {"raw": raw}}
            ).execute()
        )
        draft_id = draft["id"]
        logger.info("Draft created: id=%s to=%s subject='%s'", draft_id, to, subject[:50])
        return (
            f"Draft created (ID: {draft_id}). "
            f"To: {to}, Subject: {subject}. "
            f"Please review the draft in Gmail before sending."
        )
    except Exception as e:
        logger.exception("gmail_send_draft failed")
        return f"Error creating draft: {e}"


async def gmail_list_labels() -> str:
    """List all Gmail labels."""
    if not settings.GMAIL_ENABLED:
        return _DISABLED_MSG
    try:
        service = await _run_sync(_build_service)
        results = await _run_sync(
            lambda: service.users().labels().list(userId="me").execute()
        )
        labels = results.get("labels", [])
        if not labels:
            return "No labels found."
        names = sorted(label["name"] for label in labels)
        return f"Gmail labels ({len(names)}):\n" + "\n".join(names)
    except Exception as e:
        logger.exception("gmail_list_labels failed")
        return f"Error listing labels: {e}"
