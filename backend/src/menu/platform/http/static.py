"""Serve la SPA compilata (`WEB_DIST_DIR`) sulla stessa origine (SR-023, SR-046; THR-074, THR-075).

Allow-list esplicita: `index.html` e pochi file alla radice, e i soli file diretti di `/assets/`
con estensione nota. Mai source map, file nascosti, cartelle o symlink che escono dalla cartella.
Una richiesta con estensione che non corrisponde a un file ammesso è 404 (mai `index.html`);
le altre GET ricadono su `index.html` (rotte della SPA). `/api*` sconosciuto è sempre 404.
"""

import gzip
import re
from email.utils import formatdate, parsedate_to_datetime
from pathlib import Path

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"
GZIP_MIN_BYTES = 500

_ROOT_FILES = frozenset(
    {
        "index.html",
        "sw.js",
        "favicon.ico",
        "favicon.svg",
        "manifest.webmanifest",
        "robots.txt",
    }
)
_CONTENT_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".webmanifest": "application/manifest+json",
    ".txt": "text/plain; charset=utf-8",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".woff2": "font/woff2",
}
_COMPRESSIBLE = frozenset({".html", ".js", ".css", ".svg", ".webmanifest", ".txt", ".ico"})
_ASSET_EXTENSIONS = frozenset(_CONTENT_TYPES) - {".html", ".txt", ".webmanifest"}
_HASHED_NAME = re.compile(r"[A-Za-z0-9_.]+-[A-Za-z0-9_-]{8,}\.[a-z0-9]+")
_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def _etag_matches(header: str, etag: str) -> bool:
    candidates = {part.strip().removeprefix("W/") for part in header.split(",")}
    return "*" in candidates or etag in candidates


class StaticSite:
    """App ASGI usata come `default` del router: viene dopo tutte le rotte dell'API."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve(strict=True)
        self._gzip_cache: dict[tuple[str, int, int], bytes] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            raise HTTPException(404)
        path: str = scope["path"]
        if scope["method"] not in ("GET", "HEAD"):
            raise HTTPException(405)
        if _is_api_path(path):
            raise HTTPException(404)
        response = self._respond(scope, path)
        await response(scope, receive, send)

    def _locate(self, path: str) -> tuple[Path, bool] | None:
        """Restituisce `(file, hashed)` per un file ammesso, `None` se non esiste (404)."""
        segments = path.split("/")[1:]
        if "" in segments[:-1] or any(s in {".", ".."} for s in segments):
            return None
        under_assets = segments[0] == "assets"
        if path == "/":
            segments = ["index.html"]
        elif under_assets:
            if len(segments) != 2 or not _SAFE_SEGMENT.fullmatch(segments[1]):
                return None
            if Path(segments[1]).suffix not in _ASSET_EXTENSIONS:
                return None
        elif len(segments) != 1 or segments[0] not in _ROOT_FILES:
            return None
        candidate = self._root.joinpath(*segments)
        try:
            real = candidate.resolve(strict=True)
        except OSError, ValueError:
            return None
        if real.parent != candidate.parent.resolve() or not real.is_relative_to(self._root):
            return None
        if candidate.is_symlink() or not real.is_file():
            return None
        return candidate, under_assets and bool(_HASHED_NAME.fullmatch(segments[1]))

    def _respond(self, scope: Scope, path: str) -> Response:
        found = self._locate(path)
        if found is None:
            last = path.rsplit("/", 1)[-1]
            is_asset_area = path == "/assets" or path.startswith("/assets/")
            hidden = any(segment.startswith(".") for segment in path.split("/"))
            if is_asset_area or hidden or "." in last or "\x00" in path or "\\" in path:
                raise HTTPException(404)
            found = (self._root / "index.html", False)
            if not found[0].is_file():
                raise HTTPException(404)
        file, hashed = found
        return self._file_response(scope, file, hashed)

    def _file_response(self, scope: Scope, file: Path, hashed: bool) -> Response:
        request_headers = Headers(scope=scope)
        stat = file.stat()
        suffix = file.suffix
        body = file.read_bytes()
        etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        encoding_gzip = (
            suffix in _COMPRESSIBLE
            and len(body) >= GZIP_MIN_BYTES
            and "gzip" in request_headers.get("accept-encoding", "").lower()
        )
        headers = {
            "Cache-Control": IMMUTABLE if hashed else REVALIDATE,
            "Last-Modified": formatdate(stat.st_mtime, usegmt=True),
            "Vary": "Accept-Encoding",
        }
        if encoding_gzip:
            etag = etag[:-1] + '-gz"'
            key = (str(file), stat.st_mtime_ns, stat.st_size)
            if key not in self._gzip_cache:
                self._gzip_cache[key] = gzip.compress(body, compresslevel=9, mtime=0)
            body = self._gzip_cache[key]
            headers["Content-Encoding"] = "gzip"
        headers["ETag"] = etag

        if self._not_modified(request_headers, etag, stat.st_mtime):
            return Response(status_code=304, headers=headers)

        headers["Content-Type"] = _CONTENT_TYPES[suffix]
        if scope["method"] == "HEAD":
            headers["Content-Length"] = str(len(body))
            return Response(status_code=200, headers=headers)
        return Response(content=body, status_code=200, headers=headers)

    @staticmethod
    def _not_modified(headers: Headers, etag: str, mtime: float) -> bool:
        if_none_match = headers.get("if-none-match")
        if if_none_match is not None:
            return _etag_matches(if_none_match, etag)
        since = headers.get("if-modified-since")
        if since is None:
            return False
        try:
            return int(mtime) <= parsedate_to_datetime(since).timestamp()
        except TypeError, ValueError:
            return False
