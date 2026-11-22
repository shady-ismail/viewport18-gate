"""Cross-platform Chromium discovery, SSRF validation, and ephemeral HTTP server helpers."""

from __future__ import annotations

import functools
import glob
import http.server
import ipaddress
import os
import posixpath
import re
import socket
import threading
import time
import urllib.parse
from pathlib import Path

_REVISION_RE = re.compile(r"(?:chromium_headless_shell|chromium)-(\d+)")


def _revision_sort_key(path_str: str) -> tuple[int, str]:
    match = _REVISION_RE.search(path_str)
    rev = int(match.group(1)) if match else -1
    return (rev, path_str)


def find_chromium_exec(explicit_path: str | None = None) -> str | None:
    """Resolve a Chromium / headless-shell binary without hardcoded user paths.

    Order of precedence:
      1. Explicit path argument (if provided, is a regular executable file).
      2. ``VIEWPORT18_CHROMIUM_PATH`` environment variable (if set and executable).
      3. ``PLAYWRIGHT_BROWSERS_PATH`` cache directory (if set and not ``"0"``).
      4. Standard per-user Playwright cache directories under ``Path.home()``.

    Returns ``None`` if no candidate is found so Playwright uses its own default.
    """
    candidates: list[str] = []
    if explicit_path:
        candidates.append(explicit_path)
    env_exec = os.environ.get("VIEWPORT18_CHROMIUM_PATH", "").strip()
    if env_exec:
        candidates.append(env_exec)

    for candidate in candidates:
        p = Path(candidate).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)

    cache_roots: list[Path] = []
    pw_browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if pw_browsers and pw_browsers != "0":
        cache_roots.append(Path(pw_browsers).expanduser())

    home = Path.home()
    cache_roots.extend(
        [
            home / "Library" / "Caches" / "ms-playwright",
            home / ".cache" / "ms-playwright",
            home / "AppData" / "Local" / "ms-playwright",
        ]
    )

    rel_patterns = (
        "chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
        "chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell.exe",
        "chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "chromium-*/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "chromium-*/chrome-linux64/chrome",
        "chromium-*/chrome-linux/chrome",
        "chromium-*/chrome-win64/chrome.exe",
    )

    for root in cache_roots:
        if not root.is_dir():
            continue
        for rel in rel_patterns:
            hits = sorted(glob.glob(str(root / rel)), key=_revision_sort_key, reverse=True)
            for hit in hits:
                hp = Path(hit)
                if hp.is_file() and os.access(hp, os.X_OK):
                    return hit
    return None


def _is_disallowed_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def validate_http_target(url: str, *, allow_private_network: bool = False) -> urllib.parse.SplitResult:
    """Validate an HTTP(S) target URL and enforce SSRF protection by default."""
    if "\x00" in url:
        raise ValueError("Target URL contains null byte")
    parsed = urllib.parse.urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme {parsed.scheme!r}; only http:// and https:// are allowed")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Invalid HTTP(S) URL target (missing host): {url!r}")

    if allow_private_network:
        return parsed

    lowered = hostname.lower()
    if lowered in ("localhost", "localhost.localdomain") or lowered.endswith(".localhost"):
        raise ValueError(
            f"Refusing loopback host {hostname!r} without --allow-private-network"
        )

    try:
        ip_literal = ipaddress.ip_address(hostname)
    except ValueError:
        ip_literal = None

    if ip_literal is not None:
        if _is_disallowed_ip(ip_literal):
            raise ValueError(
                f"Refusing non-public IP address {hostname!r} without --allow-private-network"
            )
        return parsed

    try:
        port = parsed.port or (443 if scheme == "https" else 80)
        addrinfo = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError:
        # Defer unreachable DNS errors to Playwright navigation rather than blocking offline tests,
        # unless the literal hostname is a blocked localhost/IP.
        return parsed

    for _, _, _, _, sockaddr in addrinfo:
        addr_str = sockaddr[0].split("%", 1)[0]
        try:
            resolved_ip = ipaddress.ip_address(addr_str)
        except ValueError:
            continue
        if _is_disallowed_ip(resolved_ip):
            raise ValueError(
                f"Refusing host {hostname!r} resolving to non-public IP {addr_str!r} "
                "without --allow-private-network"
            )
    return parsed


def wait_for_port(host: str, port: int, timeout_sec: float = 3.0) -> None:
    """Wait until local TCP port accepts connections."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.02)
    raise TimeoutError(f"Local HTTP server failed to bind on {host}:{port} within {timeout_sec}s")


def start_local_server(target_dir: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    """Start an ephemeral localhost-only static HTTP server rooted at ``target_dir``."""
    resolved_root = target_dir.resolve()

    class SafeStaticHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(resolved_root), **kwargs)

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

        def do_POST(self) -> None:  # noqa: N802
            self.send_error(405, "Method Not Allowed")

        def do_PUT(self) -> None:  # noqa: N802
            self.send_error(405, "Method Not Allowed")

        def do_DELETE(self) -> None:  # noqa: N802
            self.send_error(405, "Method Not Allowed")

        def translate_path(self, path: str) -> str:
            parsed = urllib.parse.urlsplit(path).path
            if "\x00" in parsed:
                return str(resolved_root / "__blocked_null__")
            clean = posixpath.normpath(urllib.parse.unquote(parsed))
            parts = [p for p in clean.split("/") if p and p not in (".", "..")]
            candidate = resolved_root
            for part in parts:
                if part.startswith(".") or "\\" in part:
                    return str(resolved_root / "__blocked_dotfile__")
                candidate = candidate / part
            try:
                resolved_cand = candidate.resolve()
                resolved_cand.relative_to(resolved_root)
            except (OSError, ValueError):
                return str(resolved_root / "__blocked_traversal__")
            return str(resolved_cand)

        def copyfile(self, source, outputfile) -> None:
            try:
                super().copyfile(source, outputfile)
            except BrokenPipeError:
                pass

    handler = functools.partial(SafeStaticHandler)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    wait_for_port("127.0.0.1", port)
    return httpd, port
