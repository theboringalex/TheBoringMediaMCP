"""Shared plumbing: HTTP client, tool registry, call log, output rendering."""

import functools
import json
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Optional

import httpx
from mcp.server.fastmcp.exceptions import ToolError

from .config import CONFIG, SERVICES

# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------


class ServiceError(ToolError):
    """Raised for any expected failure; the message is shown to the AI client."""


# ---------------------------------------------------------------------------
# call log (in memory, secrets never stored)
# ---------------------------------------------------------------------------

CALL_LOG: deque = deque(maxlen=200)


def log_call(tool: str, service: str, ok: bool, ms: int, note: str = "") -> None:
    CALL_LOG.appendleft({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "tool": tool,
                         "service": service, "ok": ok, "ms": ms, "note": note[:200]})


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


@dataclass
class ToolDef:
    service: str
    name: str
    fn: Callable
    kind: str  # read | write | destructive
    title: str
    description: str
    mixed: bool = False  # visible in read-only mode, the tool decides per call


REGISTRY: dict[str, ToolDef] = {}
PINGS: dict[str, Callable] = {}


def render(out: Any) -> str:
    if isinstance(out, str):
        text = out
    else:
        text = json.dumps(out, ensure_ascii=False, separators=(",", ":"), default=str)
    limit = CONFIG.max_chars()
    if len(text) > limit:
        cut = len(text) - limit
        text = text[:limit] + f"\n…[truncated, {cut} more characters — use filters, limit/offset or a narrower query]"
    return text


def tool(service: str, kind: str = "read", title: Optional[str] = None, mixed: bool = False):
    """Register a tool. kind: read | write | destructive.

    mixed=True: the tool stays visible in read-only mode and checks per call
    (used by the generic *_api_request tools: GET is fine, everything else is not).
    """

    def deco(fn: Callable):
        name = fn.__name__

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            t0 = time.time()
            svc = CONFIG.service(service)
            if not svc["enabled"]:
                raise ServiceError(f"Service '{service}' is disabled. Enable it in the TheBoringMediaMCP web UI.")
            if kind != "read" and svc["read_only"] and not mixed:
                raise ServiceError(f"Service '{service}' is in read-only mode; '{name}' changes data.")
            try:
                out = await fn(*args, **kwargs)
                text = render(out)
                log_call(name, service, True, int((time.time() - t0) * 1000))
                return text
            except ToolError as e:
                log_call(name, service, False, int((time.time() - t0) * 1000), str(e))
                raise
            except Exception as e:  # unexpected
                log_call(name, service, False, int((time.time() - t0) * 1000), repr(e))
                raise ServiceError(f"{name} failed: {e!r}")

        doc = (fn.__doc__ or "").strip()
        REGISTRY[name] = ToolDef(service, name, wrapper, kind,
                                 title or name.replace("_", " ").title(), doc, mixed)
        return wrapper

    return deco


def ping(service: str):
    def deco(fn):
        PINGS[service] = fn
        return fn
    return deco


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _auth(service: str, cfg: dict) -> tuple[dict, Optional[httpx.BasicAuth], dict]:
    headers: dict[str, str] = {}
    auth = None
    params: dict[str, str] = {}
    key = cfg.get("api_key", "")
    if service == "jellyfin":
        if key:
            headers["X-Emby-Token"] = key
            headers["Authorization"] = f'MediaBrowser Token="{key}"'
    elif service in ("radarr", "sonarr", "prowlarr", "seerr"):
        if key:
            headers["X-Api-Key"] = key
    elif service == "sabnzbd":
        if key:
            params["apikey"] = key
    elif service == "gluetun":
        if key:
            headers["X-API-Key"] = key
        elif cfg.get("username"):
            auth = httpx.BasicAuth(cfg["username"], cfg.get("password", ""))
    elif service == "homarr":
        if key:
            headers["ApiKey"] = key
    return headers, auth, params


def _base(service: str, cfg: dict) -> str:
    url = (cfg.get("url") or "").strip().rstrip("/")
    if not url:
        raise ServiceError(f"No URL configured for '{service}'.")
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


async def call(
    service: str,
    method: str,
    path: str,
    *,
    params: Optional[dict] = None,
    body: Any = None,
    form: Optional[dict] = None,
    timeout: float = 30.0,
    expect: str = "auto",
    cfg_override: Optional[dict] = None,
) -> Any:
    """Call a service API. Returns parsed JSON (or text). Raises ServiceError."""
    cfg = cfg_override if cfg_override is not None else CONFIG.service(service)
    if not path.startswith("/"):
        raise ServiceError("path must start with '/'")
    if "://" in path or ".." in path.split("?")[0].split("/"):
        raise ServiceError("path must be a plain path on the configured service")
    base = _base(service, cfg)
    headers, auth, auth_params = _auth(service, cfg)
    q = {k: v for k, v in (params or {}).items() if v is not None}
    q.update(auth_params)
    method = method.upper()
    try:
        async with httpx.AsyncClient(verify=cfg.get("verify_ssl", True), timeout=timeout,
                                     follow_redirects=True, auth=auth) as client:
            r = await client.request(method, base + path, params=q or None, headers=headers,
                                     json=body if body is not None else None, data=form)
    except httpx.ConnectError as e:
        raise ServiceError(f"{service}: cannot connect to {base} ({e})")
    except httpx.TimeoutException:
        raise ServiceError(f"{service}: timeout after {timeout:.0f}s")
    except httpx.HTTPError as e:
        raise ServiceError(f"{service}: HTTP error {e!r}")
    if r.status_code >= 400:
        detail = r.text.strip()[:600]
        if r.status_code in (401, 403):
            detail = "authentication failed – check the API key. " + detail
        raise ServiceError(f"{service} {method} {path} → HTTP {r.status_code}: {detail}")
    if r.status_code == 204 or not r.content:
        return {"ok": True, "status": r.status_code}
    ctype = r.headers.get("content-type", "")
    if expect == "text" or (expect == "auto" and "json" not in ctype):
        try:
            return r.json()
        except Exception:
            return r.text
    try:
        return r.json()
    except Exception:
        return r.text


def pick(obj: Any, keys: list[str]) -> Any:
    """Keep only some keys of a dict (or of each dict in a list)."""
    if isinstance(obj, list):
        return [pick(o, keys) for o in obj]
    if isinstance(obj, dict):
        return {k: obj[k] for k in keys if k in obj}
    return obj


def page(items: list, limit: int, offset: int = 0) -> dict:
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    return {"total": len(items), "offset": offset, "items": items[offset:offset + limit]}


def service_title(name: str) -> str:
    return SERVICES[name]["title"]


# ---------------------------------------------------------------------------
# helpers shared by tools
# ---------------------------------------------------------------------------

import re  # noqa: E402

_SECRET_KEY = re.compile(r"(api_?key|private_?key|preshared|passw|token|secret|nzb_?key|^key$|credential)", re.I)


def redact(obj: Any) -> Any:
    """Mask values of secret-looking keys so they never reach the AI client."""
    if isinstance(obj, dict):
        return {k: ("***" if _SECRET_KEY.search(str(k)) and v not in (None, "", False) else redact(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(o) for o in obj]
    return obj


def guard_write(service: str, method: str) -> None:
    if method.upper() not in ("GET", "HEAD") and CONFIG.service(service)["read_only"]:
        raise ServiceError(f"Service '{service}' is in read-only mode; only GET requests are allowed.")


async def generic(service: str, method: str, path: str, query: Optional[dict], body: Any, timeout: float = 60.0) -> Any:
    method = method.upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"):
        raise ServiceError("method must be GET, POST, PUT, PATCH, DELETE or HEAD")
    guard_write(service, method)
    return redact(await call(service, method, path, params=query, body=body, timeout=timeout))
