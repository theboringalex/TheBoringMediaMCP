"""MCP server assembly, HTTP app, authentication and web-UI API."""

import asyncio
import base64
import contextlib
import hmac
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from . import tools  # noqa: F401  (registers all tools)
from .config import CONFIG, GROUPS, SERVICES, TOOL_LIMIT_HINT, VERSION
from .core import CALL_LOG, PINGS, REGISTRY, ServiceError

log = logging.getLogger("theboringmediamcp")
WEB = Path(__file__).parent / "web"

# ---------------------------------------------------------------------------
# scopes: which tools are exposed on which endpoint
# ---------------------------------------------------------------------------

SCOPES: dict[str, dict[str, Any]] = {"all": {"path": "/mcp", "services": list(SERVICES), "title": "All services"}}
for _g, _members in GROUPS.items():
    SCOPES[_g] = {"path": f"/mcp/{_g}", "services": _members,
                  "title": {"arr": "Radarr · Sonarr · Prowlarr · Seerr",
                            "downloads": "SABnzbd · Gluetun",
                            "media": "Jellyfin · Jellyfin Collection"}[_g]}
for _s, _m in SERVICES.items():
    SCOPES[_s] = {"path": f"/mcp/{_s}", "services": [_s], "title": _m["title"]}


def _visible(name: str) -> bool:
    td = REGISTRY[name]
    svc = CONFIG.service(td.service)
    if not svc["enabled"]:
        return False
    if svc["read_only"] and td.kind != "read" and not td.mixed:
        return False
    return True


class ScopedMCP(FastMCP):
    """FastMCP that only lists tools of enabled services (re-evaluated on every request)."""

    async def list_tools(self):  # type: ignore[override]
        tools_ = await super().list_tools()
        return [t for t in tools_ if t.name in REGISTRY and _visible(t.name)]


def build_mcp(scope: str, *, host: str = "0.0.0.0", port: int = 17830) -> ScopedMCP:
    meta = SCOPES[scope]
    mcp = ScopedMCP(
        name="TheBoringMediaMCP" if scope == "all" else f"TheBoringMediaMCP/{scope}",
        instructions=(
            "Control a self-hosted media stack (Jellyfin, Radarr, Sonarr, Prowlarr, Seerr, SABnzbd, Gluetun, "
            "Homarr, Jellyfin Collection). Tool names start with the service name. "
            "Workflow hints: use *_lookup / seerr_search to find a title before *_add_movie / *_add_series / "
            "seerr_create_request; check *_queue and sabnzbd_status for download progress; "
            "destructive tools (delete/remove/restart) change real data – confirm with the user first."),
        host=host, port=port,
        streamable_http_path=meta["path"], stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    for td in REGISTRY.values():
        if td.service in meta["services"]:
            mcp.add_tool(
                td.fn, name=td.name, title=td.title, description=td.description,
                annotations=ToolAnnotations(
                    title=td.title,
                    readOnlyHint=(td.kind == "read"),
                    destructiveHint=(td.kind == "destructive"),
                    idempotentHint=(td.kind == "read"),
                    openWorldHint=False),
                structured_output=False)
    return mcp


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------

_FAILS: dict[str, list[float]] = {}


def _rate_limited(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _FAILS.get(ip, []) if now - t < 300]
    _FAILS[ip] = hits
    return len(hits) >= 15


def _note_fail(ip: str) -> None:
    _FAILS.setdefault(ip, []).append(time.time())


def _token_ok(candidate: Optional[str]) -> bool:
    tok = str(CONFIG.general("mcp_token") or "")
    return bool(candidate) and bool(tok) and hmac.compare_digest(candidate.encode(), tok.encode())


def _headers(scope) -> dict[str, str]:
    return {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}


def _bearer(scope) -> Optional[str]:
    h = _headers(scope)
    a = h.get("authorization", "")
    if a.lower().startswith("bearer "):
        return a[7:].strip()
    if h.get("x-api-key"):
        return h["x-api-key"].strip()
    q = scope.get("query_string", b"").decode()
    m = re.search(r"(?:^|&)token=([^&]+)", q)
    return m.group(1) if m else None


def _client_key(scope) -> str:
    """Key for the failed-login limiter: the proxy's X-Forwarded-For if present (not used for any trust decision)."""
    xff = _headers(scope).get("x-forwarded-for", "")
    return xff.split(",")[0].strip() or (scope.get("client") or ("?", 0))[0]


def _is_ingress(scope) -> bool:
    client = (scope.get("client") or ("", 0))[0]
    return client == "172.30.32.2" and "x-ingress-path" in _headers(scope)


PROTECTED = re.compile(r"^/(mcp(/|$)|sse$|messages(/|$)|api/ui(/|$))")
SECRET_PREFIX = re.compile(r"^/s/([^/]+)(/.*)?$")


class AuthMiddleware:
    """Bearer token (Authorization / X-API-Key / ?token=) or secret path /s/<token>/mcp."""

    def __init__(self, app):
        self.app = app

    async def _deny(self, scope, receive, send, code=401, msg="Unauthorized"):
        resp = JSONResponse({"error": msg}, status_code=code,
                            headers={"WWW-Authenticate": 'Bearer realm="TheBoringMediaMCP"'} if code == 401 else None)
        await resp(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        ip = _client_key(scope)
        path = scope["path"]
        authed = False

        m = SECRET_PREFIX.match(path)
        if m:
            if _rate_limited(ip):
                return await self._deny(scope, receive, send, 429, "Too many failed attempts")
            if not _token_ok(m.group(1)):
                _note_fail(ip)
                return await self._deny(scope, receive, send)
            authed = True
            prefix = f"/s/{m.group(1)}"
            new_path = m.group(2) or "/"
            scope = dict(scope)
            scope["root_path"] = scope.get("root_path", "") + prefix
            scope["path"] = new_path
            scope["raw_path"] = new_path.encode()
            path = new_path

        if PROTECTED.match(path) and not authed:
            if path.startswith("/api/ui") and _is_ingress(scope):
                authed = True
            else:
                if _rate_limited(ip):
                    return await self._deny(scope, receive, send, 429, "Too many failed attempts")
                if _token_ok(_bearer(scope)):
                    authed = True
                else:
                    _note_fail(ip)
                    return await self._deny(scope, receive, send)
        return await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# web UI api
# ---------------------------------------------------------------------------


def _tool_list(service: str) -> list[dict]:
    return [{"name": t.name, "kind": t.kind, "mixed": t.mixed, "title": t.title,
             "description": t.description.split("\n")[0]}
            for t in REGISTRY.values() if t.service == service]


def _scope_counts() -> dict[str, int]:
    visible = {n for n in REGISTRY if _visible(n)}
    return {sid: sum(1 for n in visible if REGISTRY[n].service in meta["services"])
            for sid, meta in SCOPES.items()}


async def api_state(request: Request) -> Response:
    services = []
    for sid, meta in SERVICES.items():
        cfg = CONFIG.service(sid)
        fields = []
        for f in meta["fields"]:
            raw = cfg.get(f["key"], "")
            fields.append({**f, "value": "" if f["secret"] else raw, "has_value": bool(raw)})
        tl = _tool_list(sid)
        services.append({
            "id": sid, "title": meta["title"], "desc": meta["desc"], "group": meta["group"], "color": meta["color"],
            "enabled": cfg["enabled"], "read_only": cfg["read_only"], "verify_ssl": cfg["verify_ssl"],
            "fields": fields, "tools": tl, "tool_count": len(tl)})
    counts = _scope_counts()
    return JSONResponse({
        "version": VERSION,
        "token": str(CONFIG.general("mcp_token") or ""),
        "public_url": str(CONFIG.general("public_url") or ""),
        "language": str(CONFIG.general("language") or "de"),
        "ingress": _is_ingress(request.scope),
        "tool_limit": TOOL_LIMIT_HINT,
        "services": services,
        "scopes": [{"id": sid, "path": m["path"], "title": m["title"], "tools": counts[sid],
                    "services": m["services"]} for sid, m in SCOPES.items()],
    })


async def api_config(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    patch: dict[str, Any] = {}
    gen = body.get("general") or {}
    if "public_url" in gen:
        patch["public_url"] = str(gen["public_url"] or "").strip().rstrip("/")
    if gen.get("language") in ("de", "en"):
        patch["language"] = gen["language"]
    for sid, vals in (body.get("services") or {}).items():
        if sid not in SERVICES:
            continue
        for k in ("enabled", "read_only", "verify_ssl"):
            if k in vals:
                patch[f"{sid}_{k}"] = bool(vals[k])
        for f in SERVICES[sid]["fields"]:
            if f["key"] in vals and vals[f["key"]] is not None:
                patch[f"{sid}_{f['key']}"] = str(vals[f["key"]]).strip()
    if patch:
        CONFIG.set_many(patch)
    return JSONResponse({"ok": True, "saved": len(patch)})


async def api_test(request: Request) -> Response:
    sid = request.path_params["sid"]
    if sid not in PINGS:
        return JSONResponse({"ok": False, "error": "unknown service"}, status_code=404)
    cfg = CONFIG.service(sid)
    try:
        body = await request.json()
    except Exception:
        body = {}
    for f in SERVICES[sid]["fields"]:
        v = (body.get("fields") or {}).get(f["key"])
        if v:  # empty secret fields keep the saved value
            cfg[f["key"]] = str(v).strip()
    if "verify_ssl" in body:
        cfg["verify_ssl"] = bool(body["verify_ssl"])
    t0 = time.time()
    try:
        res = await asyncio.wait_for(PINGS[sid](cfg), timeout=40)
        return JSONResponse({"ok": True, "ms": int((time.time() - t0) * 1000), **res})
    except ServiceError as e:
        return JSONResponse({"ok": False, "ms": int((time.time() - t0) * 1000), "error": str(e)})
    except asyncio.TimeoutError:
        return JSONResponse({"ok": False, "error": "timeout"})
    except Exception as e:  # pragma: no cover
        return JSONResponse({"ok": False, "error": repr(e)})


async def api_log(request: Request) -> Response:
    return JSONResponse({"items": list(CALL_LOG)})


async def api_token(request: Request) -> Response:
    return JSONResponse({"token": CONFIG.regenerate_token()})


def _file(name: str, media: str) -> Response:
    p = WEB / name
    if not p.is_file() and name.endswith(".png") and (WEB / "logo.b64").is_file():
        # the logo ships as base64 text (logo.b64) – used for /logo.png and /favicon.png
        return Response(base64.b64decode((WEB / "logo.b64").read_text()), media_type=media,
                        headers={"Cache-Control": "public, max-age=86400"})
    if not p.is_file():
        return Response("not found", status_code=404)
    return FileResponse(p, media_type=media, headers={"Cache-Control": "no-cache"})


async def index(request: Request) -> Response:
    return _file("index.html", "text/html; charset=utf-8")


async def healthz(request: Request) -> Response:
    return JSONResponse({"status": "ok", "version": VERSION,
                         "services": CONFIG.enabled_services()})


# ---------------------------------------------------------------------------
# app factory
# ---------------------------------------------------------------------------


def create_app(host: str = "0.0.0.0", port: int = 17830) -> Starlette:
    created = not str(CONFIG.general("mcp_token") or "")
    tok = CONFIG.ensure_token()
    if created:
        log.warning("Generated MCP access token (also visible in the web UI): %s", tok)

    servers = {sid: build_mcp(sid, host=host, port=port) for sid in SCOPES}
    routes: list = [
        Route("/", index), Route("/healthz", healthz),
        Route("/logo.png", lambda r: _file("logo.png", "image/png")),
        Route("/favicon.png", lambda r: _file("favicon.png", "image/png")),
        Route("/api/ui/state", api_state), Route("/api/ui/config", api_config, methods=["POST"]),
        Route("/api/ui/test/{sid}", api_test, methods=["POST"]),
        Route("/api/ui/log", api_log), Route("/api/ui/token", api_token, methods=["POST"]),
    ]
    # Streamable HTTP (current standard) on /mcp and /mcp/<scope>
    for sid, mcp in servers.items():
        routes += mcp.streamable_http_app().routes
    # Legacy HTTP+SSE transport (older clients) on /sse
    routes += servers["all"].sse_app().routes

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with contextlib.AsyncExitStack() as stack:
            for mcp in servers.values():
                await stack.enter_async_context(mcp.session_manager.run())
            yield

    return Starlette(
        routes=routes, lifespan=lifespan,
        middleware=[
            Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["mcp-session-id"]),
            Middleware(AuthMiddleware),
        ])
