"""Spotify playback control and search via spotipy."""
import asyncio
import logging

from jarvis.config import settings

logger = logging.getLogger("jarvis.tools.spotify")

SCOPES = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing "
    "playlist-read-private"
)

_DISABLED_MSG = "Spotify integration is disabled. Set SPOTIFY_ENABLED=true to enable it."


def _get_client():
    """Build an authenticated spotipy client."""
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

    auth = SpotifyOAuth(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
        redirect_uri=settings.SPOTIFY_REDIRECT_URI,
        scope=SCOPES,
        cache_path=str(settings.DATA_DIR / ".spotify_cache"),
    )
    return spotipy.Spotify(auth_manager=auth)


async def _run(func, *args):
    """Run a blocking spotipy call in the default executor."""
    return await asyncio.get_event_loop().run_in_executor(None, func, *args)


async def spotify_now_playing() -> str:
    """Return the currently playing track info."""
    if not settings.SPOTIFY_ENABLED:
        return _DISABLED_MSG
    try:
        sp = _get_client()
        pb = await _run(sp.current_playback)
        if not pb or not pb.get("item"):
            return "Nothing is currently playing on Spotify."
        item = pb["item"]
        name = item["name"]
        artist = ", ".join(a["name"] for a in item.get("artists", []))
        album = item.get("album", {}).get("name", "")
        progress_ms = pb.get("progress_ms", 0)
        duration_ms = item.get("duration_ms", 0)
        prog = f"{progress_ms // 60000}:{(progress_ms // 1000) % 60:02d}"
        dur = f"{duration_ms // 60000}:{(duration_ms // 1000) % 60:02d}"
        state = "Playing" if pb.get("is_playing") else "Paused"
        return f"{state}: {name} by {artist} — {album} [{prog}/{dur}]"
    except Exception as e:
        logger.error("spotify_now_playing error: %s", e)
        return f"Spotify error: {e}"


async def spotify_play_pause() -> str:
    """Toggle playback between play and pause."""
    if not settings.SPOTIFY_ENABLED:
        return _DISABLED_MSG
    try:
        sp = _get_client()
        pb = await _run(sp.current_playback)
        if not pb:
            return "No active Spotify device found."
        if pb.get("is_playing"):
            await _run(sp.pause_playback)
            return "Spotify paused."
        else:
            await _run(sp.start_playback)
            return "Spotify resumed."
    except Exception as e:
        if "NO_ACTIVE_DEVICE" in str(e) or "No active device" in str(e):
            return "No active Spotify device found. Open Spotify on a device first."
        logger.error("spotify_play_pause error: %s", e)
        return f"Spotify error: {e}"


async def spotify_next_track() -> str:
    """Skip to the next track."""
    if not settings.SPOTIFY_ENABLED:
        return _DISABLED_MSG
    try:
        sp = _get_client()
        await _run(sp.next_track)
        return "Skipped to next track."
    except Exception as e:
        if "NO_ACTIVE_DEVICE" in str(e):
            return "No active Spotify device found."
        logger.error("spotify_next_track error: %s", e)
        return f"Spotify error: {e}"


async def spotify_previous_track() -> str:
    """Go back to the previous track."""
    if not settings.SPOTIFY_ENABLED:
        return _DISABLED_MSG
    try:
        sp = _get_client()
        await _run(sp.previous_track)
        return "Went back to previous track."
    except Exception as e:
        if "NO_ACTIVE_DEVICE" in str(e):
            return "No active Spotify device found."
        logger.error("spotify_previous_track error: %s", e)
        return f"Spotify error: {e}"


async def spotify_search(query: str, search_type: str = "track", limit: int = 5) -> str:
    """Search Spotify for tracks, artists, albums, or playlists."""
    if not settings.SPOTIFY_ENABLED:
        return _DISABLED_MSG
    valid_types = {"track", "artist", "album", "playlist"}
    if search_type not in valid_types:
        return f"Invalid search type '{search_type}'. Use: {', '.join(sorted(valid_types))}"
    try:
        sp = _get_client()
        results = await _run(sp.search, query, limit, 0, search_type)
        key = search_type + "s"
        items = results.get(key, {}).get("items", [])
        if not items:
            return f"No {search_type} results for '{query}'."
        lines = [f"Spotify {search_type} results for '{query}':"]
        for i, item in enumerate(items, 1):
            if search_type == "track":
                artist = ", ".join(a["name"] for a in item.get("artists", []))
                lines.append(f"{i}. {item['name']} by {artist}")
            elif search_type == "artist":
                followers = item.get("followers", {}).get("total", 0)
                lines.append(f"{i}. {item['name']} ({followers:,} followers)")
            elif search_type == "album":
                artist = ", ".join(a["name"] for a in item.get("artists", []))
                lines.append(f"{i}. {item['name']} by {artist}")
            else:
                owner = item.get("owner", {}).get("display_name", "")
                lines.append(f"{i}. {item['name']} by {owner}")
        return "\n".join(lines)
    except Exception as e:
        logger.error("spotify_search error: %s", e)
        return f"Spotify error: {e}"


async def spotify_play_track(query: str) -> str:
    """Search for a track and play the first result."""
    if not settings.SPOTIFY_ENABLED:
        return _DISABLED_MSG
    try:
        sp = _get_client()
        results = await _run(sp.search, query, 1, 0, "track")
        tracks = results.get("tracks", {}).get("items", [])
        if not tracks:
            return f"No tracks found for '{query}'."
        track = tracks[0]
        uri = track["uri"]
        name = track["name"]
        artist = ", ".join(a["name"] for a in track.get("artists", []))
        await _run(lambda: sp.start_playback(uris=[uri]))
        return f"Now playing: {name} by {artist}"
    except Exception as e:
        if "NO_ACTIVE_DEVICE" in str(e):
            return "No active Spotify device found. Open Spotify on a device first."
        logger.error("spotify_play_track error: %s", e)
        return f"Spotify error: {e}"


async def spotify_set_volume(volume: int) -> str:
    """Set Spotify playback volume (0-100)."""
    if not settings.SPOTIFY_ENABLED:
        return _DISABLED_MSG
    if not 0 <= volume <= 100:
        return "Volume must be between 0 and 100."
    try:
        sp = _get_client()
        await _run(sp.volume, volume)
        return f"Spotify volume set to {volume}%."
    except Exception as e:
        if "NO_ACTIVE_DEVICE" in str(e):
            return "No active Spotify device found."
        logger.error("spotify_set_volume error: %s", e)
        return f"Spotify error: {e}"


async def spotify_get_playlists(limit: int = 10) -> str:
    """List the user's Spotify playlists."""
    if not settings.SPOTIFY_ENABLED:
        return _DISABLED_MSG
    try:
        sp = _get_client()
        results = await _run(sp.current_user_playlists, limit)
        items = results.get("items", [])
        if not items:
            return "No playlists found."
        total = results.get("total", len(items))
        lines = [f"Your Spotify playlists ({total} total):"]
        for i, pl in enumerate(items, 1):
            track_count = pl.get("tracks", {}).get("total", 0)
            lines.append(f"{i}. {pl['name']} ({track_count} tracks)")
        if total > limit:
            lines.append(f"...and {total - limit} more.")
        return "\n".join(lines)
    except Exception as e:
        logger.error("spotify_get_playlists error: %s", e)
        return f"Spotify error: {e}"
