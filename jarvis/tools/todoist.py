"""Todoist integration via the REST API v2."""
import logging

import httpx

from jarvis.config import settings

logger = logging.getLogger("jarvis.tools.todoist")

_BASE_URL = "https://api.todoist.com/rest/v2"
_TIMEOUT = 10.0


def _headers() -> dict[str, str]:
    """Build authorization headers for the Todoist API."""
    return {"Authorization": f"Bearer {settings.TODOIST_API_KEY}"}


async def _resolve_project_id(client: httpx.AsyncClient, project: str) -> str | None:
    """Resolve a project name to its ID, returning None if not found."""
    resp = await client.get(f"{_BASE_URL}/projects", headers=_headers())
    resp.raise_for_status()
    for p in resp.json():
        if p["name"].lower() == project.lower():
            return p["id"]
    return None


async def todoist_get_tasks(project: str = "") -> str:
    """List active tasks, optionally filtered by project name."""
    if not settings.TODOIST_ENABLED:
        return "Todoist integration is disabled."
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            params: dict[str, str] = {}
            if project:
                pid = await _resolve_project_id(client, project)
                if pid is None:
                    return f"Project '{project}' not found."
                params["project_id"] = pid
            resp = await client.get(
                f"{_BASE_URL}/tasks", headers=_headers(), params=params,
            )
            resp.raise_for_status()
        tasks = resp.json()
        if not tasks:
            return "No active tasks."
        lines = [
            f"[{t['id']}] {t['content']}"
            + (f" (due: {t['due']['string']})" if t.get("due") else "")
            for t in tasks
        ]
        return "\n".join(lines)
    except Exception as e:
        logger.error("todoist_get_tasks failed: %s", e)
        return f"Error fetching tasks: {e}"


async def todoist_add_task(
    content: str,
    due_string: str = "",
    priority: int = 1,
    project: str = "",
) -> str:
    """Add a new task."""
    if not settings.TODOIST_ENABLED:
        return "Todoist integration is disabled."
    try:
        body: dict = {"content": content, "priority": priority}
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            if due_string:
                body["due_string"] = due_string
            if project:
                pid = await _resolve_project_id(client, project)
                if pid is None:
                    return f"Project '{project}' not found."
                body["project_id"] = pid
            resp = await client.post(
                f"{_BASE_URL}/tasks", headers=_headers(), json=body,
            )
            resp.raise_for_status()
        task = resp.json()
        return f"Created task [{task['id']}]: {task['content']}"
    except Exception as e:
        logger.error("todoist_add_task failed: %s", e)
        return f"Error adding task: {e}"


async def todoist_complete_task(task_id: str) -> str:
    """Mark a task as complete."""
    if not settings.TODOIST_ENABLED:
        return "Todoist integration is disabled."
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE_URL}/tasks/{task_id}/close", headers=_headers(),
            )
            resp.raise_for_status()
        return f"Task {task_id} completed."
    except Exception as e:
        logger.error("todoist_complete_task failed for %s: %s", task_id, e)
        return f"Error completing task {task_id}: {e}"


async def todoist_get_projects() -> str:
    """List all projects."""
    if not settings.TODOIST_ENABLED:
        return "Todoist integration is disabled."
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE_URL}/projects", headers=_headers())
            resp.raise_for_status()
        projects = resp.json()
        if not projects:
            return "No projects found."
        lines = [f"[{p['id']}] {p['name']}" for p in projects]
        return "\n".join(lines)
    except Exception as e:
        logger.error("todoist_get_projects failed: %s", e)
        return f"Error fetching projects: {e}"


async def todoist_search_tasks(query: str) -> str:
    """Search/filter tasks using Todoist filter syntax."""
    if not settings.TODOIST_ENABLED:
        return "Todoist integration is disabled."
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_BASE_URL}/tasks",
                headers=_headers(),
                params={"filter": query},
            )
            resp.raise_for_status()
        tasks = resp.json()
        if not tasks:
            return f"No tasks matching '{query}'."
        lines = [
            f"[{t['id']}] {t['content']}"
            + (f" (due: {t['due']['string']})" if t.get("due") else "")
            for t in tasks
        ]
        return "\n".join(lines)
    except Exception as e:
        logger.error("todoist_search_tasks failed: %s", e)
        return f"Error searching tasks: {e}"
