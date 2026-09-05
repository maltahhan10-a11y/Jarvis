"""Home Assistant integration via the HA REST API."""
import logging

import httpx

from jarvis.config import settings

logger = logging.getLogger("jarvis.tools.home_assistant")

_TIMEOUT = 10.0
_DOMAIN_FILTER = ("light", "switch", "sensor", "climate")


def _headers() -> dict[str, str]:
    """Build authorization headers for the HA API."""
    return {"Authorization": f"Bearer {settings.HOME_ASSISTANT_TOKEN}"}


def _url(path: str) -> str:
    """Build a full HA API URL."""
    return f"{settings.HOME_ASSISTANT_URL.rstrip('/')}/api/{path.lstrip('/')}"


async def ha_list_devices() -> str:
    """List all lights, switches, sensors, and climate entities."""
    if not settings.HOME_ASSISTANT_ENABLED:
        return "Home Assistant integration is disabled."
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_url("states"), headers=_headers())
            resp.raise_for_status()
        entities = [
            e for e in resp.json()
            if e.get("entity_id", "").split(".")[0] in _DOMAIN_FILTER
        ]
        if not entities:
            return "No matching entities found."
        lines = [f"{e['entity_id']}: {e['state']}" for e in entities]
        return "\n".join(lines)
    except Exception as e:
        logger.error("ha_list_devices failed: %s", e)
        return f"Error listing devices: {e}"


async def ha_get_state(entity_id: str) -> str:
    """Get the current state of an entity."""
    if not settings.HOME_ASSISTANT_ENABLED:
        return "Home Assistant integration is disabled."
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_url(f"states/{entity_id}"), headers=_headers())
            resp.raise_for_status()
        data = resp.json()
        attrs = data.get("attributes", {})
        name = attrs.get("friendly_name", entity_id)
        return f"{name} is {data['state']}." + (
            f" Brightness: {attrs['brightness']}." if "brightness" in attrs else ""
        )
    except Exception as e:
        logger.error("ha_get_state failed for %s: %s", entity_id, e)
        return f"Error getting state for {entity_id}: {e}"


async def ha_turn_on(entity_id: str) -> str:
    """Turn on a light, switch, or other entity."""
    if not settings.HOME_ASSISTANT_ENABLED:
        return "Home Assistant integration is disabled."
    domain = entity_id.split(".")[0]
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _url(f"services/{domain}/turn_on"),
                headers=_headers(),
                json={"entity_id": entity_id},
            )
            resp.raise_for_status()
        return f"Turned on {entity_id}."
    except Exception as e:
        logger.error("ha_turn_on failed for %s: %s", entity_id, e)
        return f"Error turning on {entity_id}: {e}"


async def ha_turn_off(entity_id: str) -> str:
    """Turn off a light, switch, or other entity."""
    if not settings.HOME_ASSISTANT_ENABLED:
        return "Home Assistant integration is disabled."
    domain = entity_id.split(".")[0]
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _url(f"services/{domain}/turn_off"),
                headers=_headers(),
                json={"entity_id": entity_id},
            )
            resp.raise_for_status()
        return f"Turned off {entity_id}."
    except Exception as e:
        logger.error("ha_turn_off failed for %s: %s", entity_id, e)
        return f"Error turning off {entity_id}: {e}"


async def ha_set_brightness(entity_id: str, brightness: int) -> str:
    """Set light brightness (0-255)."""
    if not settings.HOME_ASSISTANT_ENABLED:
        return "Home Assistant integration is disabled."
    brightness = max(0, min(255, brightness))
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _url("services/light/turn_on"),
                headers=_headers(),
                json={"entity_id": entity_id, "brightness": brightness},
            )
            resp.raise_for_status()
        return f"Set {entity_id} brightness to {brightness}."
    except Exception as e:
        logger.error("ha_set_brightness failed for %s: %s", entity_id, e)
        return f"Error setting brightness for {entity_id}: {e}"


async def ha_set_temperature(entity_id: str, temperature: float) -> str:
    """Set thermostat target temperature."""
    if not settings.HOME_ASSISTANT_ENABLED:
        return "Home Assistant integration is disabled."
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _url("services/climate/set_temperature"),
                headers=_headers(),
                json={"entity_id": entity_id, "temperature": temperature},
            )
            resp.raise_for_status()
        return f"Set {entity_id} target temperature to {temperature}."
    except Exception as e:
        logger.error("ha_set_temperature failed for %s: %s", entity_id, e)
        return f"Error setting temperature for {entity_id}: {e}"
