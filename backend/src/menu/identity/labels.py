"""Etichetta del dispositivo ricavata dallo user agent (l'UA completo non si conserva)."""

import re

_BROWSERS: tuple[tuple[str, str], ...] = (
    (r"Edg(?:e|A|iOS)?/", "Edge"),
    (r"OPR/|Opera", "Opera"),
    (r"SamsungBrowser/", "Samsung Internet"),
    (r"Firefox/|FxiOS/", "Firefox"),
    (r"Chrome/|CriOS/|Chromium/", "Chrome"),
    (r"Safari/", "Safari"),
)
_SYSTEMS: tuple[tuple[str, str], ...] = (
    (r"Android", "Android"),
    (r"iPhone|iPad|iPod", "iOS"),
    (r"Windows", "Windows"),
    (r"Mac OS X|Macintosh", "macOS"),
    (r"CrOS", "ChromeOS"),
    (r"Linux|X11", "Linux"),
)
_MAX_UA = 512


def device_label(user_agent: str | None) -> str | None:
    """ "Chrome · Android" e simili; `None` se lo user agent non è riconoscibile."""
    if not user_agent:
        return None
    ua = user_agent[:_MAX_UA]
    browser = next((name for pattern, name in _BROWSERS if re.search(pattern, ua)), None)
    system = next((name for pattern, name in _SYSTEMS if re.search(pattern, ua)), None)
    parts = [p for p in (browser, system) if p]
    return " · ".join(parts) or None
