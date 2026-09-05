"""Google Calendar API integration for JARVIS."""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from jarvis.config import settings

logger = logging.getLogger("jarvis.tools.google_calendar")

SCOPES = ["https://www.googleapis.com/auth/calendar"]
_DISABLED_MSG = (
    "Google Calendar integration is not enabled. "
    "Set GOOGLE_CALENDAR_ENABLED=true in .env"
)


def _get_credentials():
    """Load or refresh OAuth credentials, running interactive flow if needed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    token_path = settings.GOOGLE_TOKEN_FILE
    creds_path = settings.GOOGLE_CREDENTIALS_FILE

    if not os.path.exists(creds_path):
        raise FileNotFoundError(
            f"Google credentials file not found at {creds_path}. "
            "Download OAuth client JSON from Google Cloud Console and place it there."
        )

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return creds


def _build_service():
    """Build a Google Calendar API service instance."""
    from googleapiclient.discovery import build

    creds = _get_credentials()
    return build("calendar", "v3", credentials=creds)


async def gcal_list_events(days: int = 1) -> str:
    """List upcoming events for the next N days."""
    if not settings.GOOGLE_CALENDAR_ENABLED:
        return _DISABLED_MSG

    days = max(1, min(days, 90))
    try:
        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days)).isoformat()

        def _fetch():
            service = _build_service()
            return (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=50,
                )
                .execute()
            )

        result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        events = result.get("items", [])

        if not events:
            return f"No events found in the next {days} day(s)."

        lines = []
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date", ""))
            summary = e.get("summary", "(No title)")
            location = e.get("location", "")
            line = f"- {summary} | {start}"
            if location:
                line += f" | Location: {location}"
            lines.append(line)

        return f"Events in the next {days} day(s):\n" + "\n".join(lines)

    except Exception as exc:
        logger.error("gcal_list_events failed: %s", exc)
        return f"Error listing events: {exc}"


async def gcal_create_event(
    title: str,
    start_time: str,
    end_time: str = "",
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
) -> str:
    """Create a calendar event with ISO 8601 datetime strings."""
    if not settings.GOOGLE_CALENDAR_ENABLED:
        return _DISABLED_MSG

    try:
        # Default to 1-hour duration if no end time
        if not end_time:
            start_dt = datetime.fromisoformat(start_time)
            end_dt = start_dt + timedelta(hours=1)
            end_time = end_dt.isoformat()

        body: dict = {
            "summary": title,
            "start": {"dateTime": start_time},
            "end": {"dateTime": end_time},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location

        def _create():
            service = _build_service()
            return (
                service.events()
                .insert(calendarId=calendar_id, body=body)
                .execute()
            )

        event = await asyncio.get_event_loop().run_in_executor(None, _create)
        link = event.get("htmlLink", "")
        logger.info("Created event '%s' (%s)", title, event.get("id"))
        return f"Event created: {title}\nLink: {link}"

    except Exception as exc:
        logger.error("gcal_create_event failed: %s", exc)
        return f"Error creating event: {exc}"


async def gcal_search_events(query: str, days: int = 30) -> str:
    """Search events by query string within the next N days."""
    if not settings.GOOGLE_CALENDAR_ENABLED:
        return _DISABLED_MSG

    days = max(1, min(days, 365))
    try:
        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days)).isoformat()

        def _search():
            service = _build_service()
            return (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    q=query,
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=50,
                )
                .execute()
            )

        result = await asyncio.get_event_loop().run_in_executor(None, _search)
        events = result.get("items", [])

        if not events:
            return f"No events matching '{query}' in the next {days} days."

        lines = []
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date", ""))
            summary = e.get("summary", "(No title)")
            lines.append(f"- {summary} | {start} | id: {e['id']}")

        return f"Found {len(lines)} event(s) matching '{query}':\n" + "\n".join(lines)

    except Exception as exc:
        logger.error("gcal_search_events failed: %s", exc)
        return f"Error searching events: {exc}"


async def gcal_delete_event(
    event_id: str, calendar_id: str = "primary"
) -> str:
    """Delete an event by its event ID."""
    if not settings.GOOGLE_CALENDAR_ENABLED:
        return _DISABLED_MSG

    try:

        def _delete():
            service = _build_service()
            service.events().delete(
                calendarId=calendar_id, eventId=event_id
            ).execute()

        await asyncio.get_event_loop().run_in_executor(None, _delete)
        logger.info("Deleted event %s from %s", event_id, calendar_id)
        return f"Event {event_id} deleted successfully."

    except Exception as exc:
        logger.error("gcal_delete_event failed: %s", exc)
        return f"Error deleting event: {exc}"


async def gcal_list_calendars() -> str:
    """List all available calendars."""
    if not settings.GOOGLE_CALENDAR_ENABLED:
        return _DISABLED_MSG

    try:

        def _list_cals():
            service = _build_service()
            return service.calendarList().list().execute()

        result = await asyncio.get_event_loop().run_in_executor(None, _list_cals)
        calendars = result.get("items", [])

        if not calendars:
            return "No calendars found."

        lines = []
        for cal in calendars:
            name = cal.get("summary", "(unnamed)")
            cal_id = cal.get("id", "")
            primary = " [primary]" if cal.get("primary") else ""
            lines.append(f"- {name}{primary} | id: {cal_id}")

        return f"Calendars ({len(lines)}):\n" + "\n".join(lines)

    except Exception as exc:
        logger.error("gcal_list_calendars failed: %s", exc)
        return f"Error listing calendars: {exc}"
