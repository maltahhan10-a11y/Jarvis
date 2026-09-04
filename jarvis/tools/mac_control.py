"""JARVIS macOS Control Tools: AppleScript-based automation for Mac apps and system."""
import asyncio
import logging

logger = logging.getLogger("jarvis.tools.mac_control")


_BLOCKED_APPLESCRIPT_PHRASES = [
    "shut down", "restart", "log out", "sleep", "power off",
]

_PROTECTED_APPS = [
    "finder", "system events", "loginwindow", "dock", "systempolicyd", "windowserver",
]


def _escape_applescript(value: str) -> str:
    """Escape a string for safe embedding in AppleScript double-quoted strings.

    Handles backslashes, double quotes, and other characters that could
    break out of an AppleScript string context.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = value.replace("\n", "\\n")
    value = value.replace("\r", "\\r")
    value = value.replace("\t", "\\t")
    return value


def _is_applescript_safe(script: str) -> tuple[bool, str]:
    """Check if an AppleScript is safe to execute."""
    script_lower = script.lower()

    for phrase in _BLOCKED_APPLESCRIPT_PHRASES:
        if phrase in script_lower:
            return False, (
                f"Blocked: script contains '{phrase}'. "
                "JARVIS cannot shut down, restart, sleep, or log out. "
                "To shut down JARVIS itself, say 'quit JARVIS' or 'exit JARVIS'."
            )

    for app in _PROTECTED_APPS:
        if app in script_lower and "quit" in script_lower:
            return False, f"Blocked: cannot quit protected system process '{app}'."

    return True, "OK"


async def run_applescript(script: str) -> str:
    """Execute an AppleScript and return the output."""
    is_safe, reason = _is_applescript_safe(script)
    if not is_safe:
        logger.warning("Blocked AppleScript: %s (reason: %s)", script[:200], reason)
        return f"Error: {reason}"

    try:
        process = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
        except TimeoutError:
            process.kill()
            return "Error: AppleScript execution timed out (30s)"

        if process.returncode != 0:
            error = stderr.decode().strip()
            logger.error("AppleScript error: %s", error)
            return f"Error: {error}"

        return stdout.decode().strip()
    except Exception as e:
        logger.error("AppleScript execution failed: %s", e)
        return f"Error: {e}"


async def open_application(app_name: str) -> str:
    """Open a macOS application by name."""
    logger.info("Opening application: %s", app_name)
    result = await run_applescript(f'tell application "{_escape_applescript(app_name)}" to activate')
    if result.startswith("Error"):
        return f"Failed to open {app_name}: {result}"
    return f"Opened {app_name} successfully."


async def close_application(app_name: str) -> str:
    """Close a macOS application by name."""
    logger.info("Closing application: %s", app_name)
    result = await run_applescript(f'tell application "{_escape_applescript(app_name)}" to quit')
    if result.startswith("Error"):
        return f"Failed to close {app_name}: {result}"
    return f"Closed {app_name}."


async def get_running_applications() -> str:
    """Get a list of currently running applications."""
    script = '''
    tell application "System Events"
        set appList to name of every process whose background only is false
        set AppleScript's text item delimiters to ", "
        return appList as text
    end tell
    '''
    result = await run_applescript(script)
    return f"Running applications: {result}"


async def get_frontmost_application() -> str:
    """Get the name of the currently focused application."""
    script = '''
    tell application "System Events"
        return name of first process whose frontmost is true
    end tell
    '''
    return await run_applescript(script)


async def open_url(url: str) -> str:
    """Open a URL in the default browser."""
    logger.info("Opening URL: %s", url)
    result = await run_applescript(f'open location "{_escape_applescript(url)}"')
    if result.startswith("Error"):
        return f"Failed to open URL: {result}"
    return f"Opened {url} in browser."


async def open_url_in_browser(url: str, browser: str = "Google Chrome") -> str:
    """Open a URL in a specific browser application."""
    logger.info("Opening URL '%s' in %s", url, browser)
    safe_browser = _escape_applescript(browser)
    safe_url = _escape_applescript(url)
    script = f'''
    tell application "{safe_browser}"
        activate
        open location "{safe_url}"
    end tell
    '''
    result = await run_applescript(script)
    if result.startswith("Error"):
        logger.warning("Direct URL open in %s failed, trying fallback.", browser)
        await run_applescript(f'tell application "{safe_browser}" to activate')
        result = await run_applescript(f'open location "{safe_url}"')
        if result.startswith("Error"):
            return f"Failed to open URL in {browser}: {result}"
    return f"Opened {url} in {browser}."


async def search_in_browser(query: str, browser: str = "Google Chrome") -> str:
    """Open a web search in a specific browser using DuckDuckGo."""
    import urllib.parse
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://duckduckgo.com/?q={encoded_query}"
    logger.info("Searching '%s' in %s", query, browser)
    return await open_url_in_browser(search_url, browser)


async def open_file(file_path: str) -> str:
    """Open a file with its default application."""
    logger.info("Opening file: %s", file_path)
    try:
        process = await asyncio.create_subprocess_exec(
            "open", file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            return f"Failed to open file: {stderr.decode().strip()}"
        return f"Opened {file_path}."
    except Exception as e:
        return f"Error opening file: {e}"


async def get_system_info() -> str:
    """Get basic system information."""
    script = '''
    set cpuInfo to do shell script "sysctl -n machdep.cpu.brand_string"
    set memInfo to do shell script "sysctl -n hw.memsize"
    set memGB to (memInfo as number) / 1073741824
    set memGB to (round (memGB * 10)) / 10
    set diskInfo to do shell script "df -H / | tail -1 | awk '{print $4}'"
    set batteryInfo to do shell script "pmset -g batt | grep -o '[0-9]*%' || echo 'N/A'"
    set uptimeInfo to do shell script "uptime | sed 's/.*up //' | sed 's/,.*//' "
    return "CPU: " & cpuInfo & "
Memory: " & memGB & " GB
Available disk: " & diskInfo & "
Battery: " & batteryInfo & "
Uptime: " & uptimeInfo
    '''
    return await run_applescript(script)


async def get_battery_status() -> str:
    """Get battery percentage and charging status."""
    try:
        process = await asyncio.create_subprocess_exec(
            "pmset", "-g", "batt",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        output = stdout.decode().strip()
        # Parse the output for useful info
        lines = output.split("\n")
        if len(lines) > 1:
            return lines[1].strip()
        return output
    except Exception as e:
        return f"Error getting battery: {e}"


async def set_volume(level: int) -> str:
    """Set system volume (0-100)."""
    level = max(0, min(100, level))
    await run_applescript(f"set volume output volume {level}")
    return f"Volume set to {level}%."


async def set_brightness(level: int) -> str:
    """Set display brightness (0-100)."""
    level = max(0, min(100, level))
    fraction = level / 100.0
    try:
        import asyncio
        process = await asyncio.create_subprocess_exec(
            "osascript", "-e",
            f'tell application "System Events" to set value of slider 1 '
            f'of group 1 of group 2 of window 1 of application process '
            f'"ControlCenter" to {fraction}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            process2 = await asyncio.create_subprocess_exec(
                "brightness", str(fraction),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process2.communicate()
            if process2.returncode != 0:
                return "Brightness adjustment requires the 'brightness' CLI tool. Install with: brew install brightness"
        return f"Brightness set to {level}%."
    except Exception as e:
        return f"Error setting brightness: {e}"


async def toggle_do_not_disturb(enable: bool) -> str:
    """Toggle Do Not Disturb / Focus mode (requires Shortcut named 'Toggle DND')."""
    action = "turn on" if enable else "turn off"
    logger.info("Do Not Disturb: %s", action)

    try:
        import asyncio
        process = await asyncio.create_subprocess_exec(
            "shortcuts", "run", "Toggle DND",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode == 0:
            return f"Do Not Disturb toggled ({action})."

        return (
            f"To {action} Do Not Disturb, I need a Shortcut named 'Toggle DND' "
            f"in your Shortcuts app. Create one that toggles the Focus mode, "
            f"and I can control it automatically."
        )
    except Exception as e:
        return f"Error toggling Do Not Disturb: {e}"


async def send_notification(title: str, message: str) -> str:
    """Send a macOS notification."""
    safe_title = _escape_applescript(title)
    safe_message = _escape_applescript(message)
    script = f'display notification "{safe_message}" with title "{safe_title}"'
    await run_applescript(script)
    return f"Notification sent: {title}"


async def get_clipboard() -> str:
    """Get the current clipboard contents."""
    try:
        process = await asyncio.create_subprocess_exec(
            "pbpaste",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        content = stdout.decode().strip()
        if not content:
            return "Clipboard is empty."
        if len(content) > 500:
            return f"Clipboard ({len(content)} chars): {content[:500]}..."
        return f"Clipboard: {content}"
    except Exception as e:
        return f"Error reading clipboard: {e}"


async def set_clipboard(text: str) -> str:
    """Set the clipboard contents."""
    try:
        process = await asyncio.create_subprocess_exec(
            "pbcopy",
            stdin=asyncio.subprocess.PIPE,
        )
        await process.communicate(input=text.encode())
        return f"Copied to clipboard ({len(text)} chars)."
    except Exception as e:
        return f"Error setting clipboard: {e}"


async def paste_to_app(text: str, app_name: str, new_document: bool = True) -> str:
    """Paste text into an application (requires macOS Accessibility permissions)."""
    logger.info("Pasting %d chars to %s (new_doc=%s)", len(text), app_name, new_document)

    try:
        process = await asyncio.create_subprocess_exec(
            "pbcopy",
            stdin=asyncio.subprocess.PIPE,
        )
        await process.communicate(input=text.encode())
    except Exception as e:
        return f"Error setting clipboard: {e}"

    safe_app = _escape_applescript(app_name)
    if new_document:
        script = f'''
        tell application "{safe_app}" to activate
        delay 0.8
        tell application "System Events"
            keystroke "n" using command down
            delay 0.5
            keystroke "v" using command down
        end tell
        '''
    else:
        script = f'''
        tell application "{safe_app}" to activate
        delay 0.5
        tell application "System Events"
            keystroke "v" using command down
        end tell
        '''

    result = await run_applescript(script)

    if result.startswith("Error"):
        if "not allowed" in result.lower() or "1002" in result:
            return (
                f"Failed to paste to {app_name}. macOS blocked the keystroke. "
                f"To fix: open System Settings > Privacy & Security > Accessibility, "
                f"then add Terminal (or your Python process) to the allowed list. "
                f"The text is still on your clipboard; you can paste manually with Cmd+V."
            )
        return f"Failed to paste to {app_name}: {result}. Text is on clipboard; try Cmd+V manually."

    return f"Pasted {len(text)} characters into {app_name} successfully."


async def get_wifi_status() -> str:
    """Get current Wi-Fi network name and status."""
    try:
        process = await asyncio.create_subprocess_exec(
            "networksetup", "-getairportnetwork", "en0",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        output = stdout.decode().strip()
        if "not associated" in output.lower():
            return "Wi-Fi is on but not connected to any network."
        return output
    except Exception as e:
        return f"Error getting Wi-Fi status: {e}"


async def toggle_wifi(enable: bool) -> str:
    """Turn Wi-Fi on or off."""
    action = "on" if enable else "off"
    try:
        process = await asyncio.create_subprocess_exec(
            "networksetup", "-setairportpower", "en0", action,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            return f"Failed to turn Wi-Fi {action}: {stderr.decode().strip()}"
        return f"Wi-Fi turned {action}."
    except Exception as e:
        return f"Error toggling Wi-Fi: {e}"


async def get_bluetooth_status() -> str:
    """Get Bluetooth power state."""
    script = '''
    do shell script "defaults read /Library/Preferences/com.apple.Bluetooth ControllerPowerState 2>/dev/null || echo -1"
    '''
    result = await run_applescript(script)
    try:
        state = int(result.strip())
        if state == 1:
            return "Bluetooth is on."
        elif state == 0:
            return "Bluetooth is off."
    except ValueError:
        pass
    return f"Bluetooth status: {result}"


async def toggle_dark_mode() -> str:
    """Toggle macOS dark mode."""
    script = '''
    tell application "System Events"
        tell appearance preferences
            set dark mode to not dark mode
            if dark mode then
                return "Dark mode enabled."
            else
                return "Light mode enabled."
            end if
        end tell
    end tell
    '''
    return await run_applescript(script)


async def get_dark_mode_status() -> str:
    """Check if dark mode is currently enabled."""
    script = '''
    tell application "System Events"
        tell appearance preferences
            if dark mode then
                return "Dark mode is on."
            else
                return "Dark mode is off (light mode)."
            end if
        end tell
    end tell
    '''
    return await run_applescript(script)


async def lock_screen() -> str:
    """Lock the screen immediately."""
    try:
        process = await asyncio.create_subprocess_exec(
            "pmset", "displaysleepnow",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        return "Screen locked."
    except Exception as e:
        return f"Error locking screen: {e}"


async def media_play_pause() -> str:
    """Toggle play/pause for the current media."""
    script = '''
    tell application "System Events"
        key code 49 using {command down}
    end tell
    '''
    try:
        process = await asyncio.create_subprocess_exec(
            "osascript", "-e",
            'tell application "System Events" to key code 16 using {command down, shift down}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
    except Exception:
        pass
    script2 = 'do shell script "osascript -e \'tell application \\"Music\\" to playpause\' 2>/dev/null || osascript -e \'tell application \\"Spotify\\" to playpause\' 2>/dev/null || echo \\"No media player responding\\""'
    return await run_applescript(script2)


async def media_next_track() -> str:
    """Skip to the next track."""
    script = 'do shell script "osascript -e \'tell application \\"Music\\" to next track\' 2>/dev/null || osascript -e \'tell application \\"Spotify\\" to next track\' 2>/dev/null || echo \\"No media player responding\\""'
    return await run_applescript(script)


async def media_previous_track() -> str:
    """Go to the previous track."""
    script = 'do shell script "osascript -e \'tell application \\"Music\\" to previous track\' 2>/dev/null || osascript -e \'tell application \\"Spotify\\" to previous track\' 2>/dev/null || echo \\"No media player responding\\""'
    return await run_applescript(script)


async def get_current_track() -> str:
    """Get the currently playing track and artist."""
    script = '''
    try
        tell application "Music"
            if player state is playing then
                set trackName to name of current track
                set artistName to artist of current track
                return "Music: " & trackName & " by " & artistName
            end if
        end tell
    end try
    try
        tell application "Spotify"
            if player state is playing then
                set trackName to name of current track
                set artistName to artist of current track
                return "Spotify: " & trackName & " by " & artistName
            end if
        end tell
    end try
    return "No music currently playing."
    '''
    return await run_applescript(script)


async def get_active_displays() -> str:
    """Get information about connected displays."""
    try:
        process = await asyncio.create_subprocess_exec(
            "system_profiler", "SPDisplaysDataType", "-json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        import json
        data = json.loads(stdout.decode())
        displays = []
        for gpu in data.get("SPDisplaysDataType", []):
            for display in gpu.get("spdisplays_ndrvs", []):
                name = display.get("_name", "Unknown")
                res = display.get("_spdisplays_resolution", "Unknown")
                displays.append(f"{name}: {res}")
        if not displays:
            return "No display information available."
        return "Connected displays:\n" + "\n".join(f"  {d}" for d in displays)
    except Exception as e:
        return f"Error getting display info: {e}"


async def get_disk_usage() -> str:
    """Get disk usage for all mounted volumes."""
    try:
        process = await asyncio.create_subprocess_exec(
            "df", "-H", "/",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        lines = stdout.decode().strip().split("\n")
        if len(lines) > 1:
            parts = lines[1].split()
            if len(parts) >= 5:
                return f"Disk: {parts[2]} used of {parts[1]} ({parts[4]} full), {parts[3]} free"
        return stdout.decode().strip()
    except Exception as e:
        return f"Error getting disk usage: {e}"


async def get_memory_pressure() -> str:
    """Get current memory usage and pressure."""
    try:
        process = await asyncio.create_subprocess_exec(
            "memory_pressure",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5.0)
        output = stdout.decode().strip()
        for line in output.split("\n"):
            if "System-wide memory" in line or "percentage" in line.lower():
                return line.strip()
        return output[:300] if output else "Could not determine memory pressure."
    except Exception as e:
        return f"Error getting memory pressure: {e}"


async def get_cpu_usage() -> str:
    """Get current CPU usage percentages."""
    try:
        process = await asyncio.create_subprocess_exec(
            "top", "-l", "1", "-n", "0", "-stats", "cpu",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10.0)
        output = stdout.decode()
        for line in output.split("\n"):
            if "CPU usage" in line:
                return line.strip()
        return "CPU usage data not available."
    except Exception as e:
        return f"Error getting CPU usage: {e}"


async def get_network_info() -> str:
    """Get local and public IP addresses."""
    try:
        local_proc = await asyncio.create_subprocess_exec(
            "ipconfig", "getifaddr", "en0",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        local_out, _ = await local_proc.communicate()
        local_ip = local_out.decode().strip() or "Not connected"

        pub_proc = await asyncio.create_subprocess_exec(
            "curl", "-s", "-m", "3", "https://api.ipify.org",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        pub_out, _ = await pub_proc.communicate()
        pub_ip = pub_out.decode().strip() or "Unavailable"

        return f"Local IP (Wi-Fi): {local_ip}\nPublic IP: {pub_ip}"
    except Exception as e:
        return f"Error getting network info: {e}"


async def get_top_processes(count: int = 5) -> str:
    """Get the top CPU-consuming processes."""
    count = max(1, min(count, 20))
    try:
        process = await asyncio.create_subprocess_exec(
            "ps", "-eo", "pid,%cpu,%mem,comm", "-r",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        lines = stdout.decode().strip().split("\n")
        header = lines[0] if lines else ""
        top_lines = lines[1:count + 1]
        return header + "\n" + "\n".join(top_lines)
    except Exception as e:
        return f"Error getting top processes: {e}"


async def kill_process(process_name: str) -> str:
    """Kill a process by name (not system-critical processes)."""
    protected = ["kernel_task", "launchd", "windowserver", "loginwindow", "dock", "finder"]
    if process_name.lower() in protected:
        return f"Cannot kill protected system process: {process_name}"
    try:
        process = await asyncio.create_subprocess_exec(
            "pkill", "-f", process_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode == 0:
            return f"Killed process: {process_name}"
        return f"No matching process found: {process_name}"
    except Exception as e:
        return f"Error killing process: {e}"


async def get_uptime() -> str:
    """Get system uptime."""
    try:
        process = await asyncio.create_subprocess_exec(
            "uptime",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        return stdout.decode().strip()
    except Exception as e:
        return f"Error getting uptime: {e}"


async def empty_trash() -> str:
    """Empty the Trash."""
    script = '''
    tell application "Finder"
        set trashCount to count of items of trash
        if trashCount is 0 then
            return "Trash is already empty."
        end if
        empty trash
        return "Trash emptied (" & trashCount & " items removed)."
    end tell
    '''
    return await run_applescript(script)


async def eject_all_disks() -> str:
    """Eject all external/removable disks."""
    script = '''
    tell application "Finder"
        set diskList to name of every disk whose ejectable is true
        if (count of diskList) is 0 then
            return "No ejectable disks found."
        end if
        repeat with diskName in diskList
            eject disk diskName
        end repeat
        set AppleScript's text item delimiters to ", "
        return "Ejected: " & (diskList as text)
    end tell
    '''
    return await run_applescript(script)


async def set_wallpaper(file_path: str) -> str:
    """Set the desktop wallpaper to a given image file."""
    safe_path = _escape_applescript(file_path)
    script = f'''
    tell application "System Events"
        tell every desktop
            set picture to "{safe_path}"
        end tell
    end tell
    return "Wallpaper set to {safe_path}"
    '''
    return await run_applescript(script)


async def write_to_app(text: str, app_name: str, new_document: bool = True) -> str:
    """Write text into an application using keystroke input (best for short text)."""
    if len(text) > 500:
        logger.info("Text too long for keystroke (%d chars), falling back to paste.", len(text))
        return await paste_to_app(text, app_name, new_document)

    logger.info("Typing %d chars into %s", len(text), app_name)

    safe_app = _escape_applescript(app_name)
    escaped_text = text.replace("\\", "\\\\").replace('"', '\\"')

    if new_document:
        script = f'''
        tell application "{safe_app}" to activate
        delay 0.8
        tell application "System Events"
            keystroke "n" using command down
            delay 0.5
            keystroke "{escaped_text}"
        end tell
        '''
    else:
        script = f'''
        tell application "{safe_app}" to activate
        delay 0.5
        tell application "System Events"
            keystroke "{escaped_text}"
        end tell
        '''

    result = await run_applescript(script)

    if result.startswith("Error"):
        if "not allowed" in result.lower() or "1002" in result:
            return (
                f"Failed to type in {app_name}. macOS blocked the keystroke. "
                f"To fix: open System Settings > Privacy & Security > Accessibility, "
                f"then add Terminal (or your Python process) to the allowed list."
            )
        return f"Failed to type in {app_name}: {result}"

    return f"Typed {len(text)} characters into {app_name} successfully."
