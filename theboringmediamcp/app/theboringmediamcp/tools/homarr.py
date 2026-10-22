"""Homarr tools (Homarr 1.x REST API + tRPC, API key in the 'ApiKey' header).

Homarr's API surface changes between releases, so besides a few convenience tools
there is `homarr_api_paths` (reads the instance's own OpenAPI spec) and the raw
`homarr_api_request` tool.
"""

from typing import Any, Optional

from ..core import ServiceError, call, generic, ping, redact, tool

S = "homarr"


@ping(S)
async def _ping(cfg: dict) -> dict:
    await call(S, "GET", "/api/health/live", cfg_override=cfg, timeout=15)
    detail = "reachable"
    if cfg.get("api_key"):
        try:
            await call(S, "GET", "/api/users/preferences", cfg_override=cfg, timeout=15)
            detail = "reachable, API key accepted"
        except ServiceError as e:
            raise ServiceError(f"Homarr is reachable but the API key was rejected: {str(e)[:160]}")
    else:
        detail = "reachable (no API key set — only public endpoints work)"
    return {"version": None, "detail": detail}


@tool(S)
async def homarr_status() -> Any:
    """Is Homarr up, and is the API key accepted?"""
    out: dict = {}
    try:
        out["live"] = await call(S, "GET", "/api/health/live", timeout=15)
    except ServiceError as e:
        return {"live": False, "error": str(e)}
    try:
        await call(S, "GET", "/api/users/preferences", timeout=15)
        out["api_key_ok"] = True
    except ServiceError as e:
        out["api_key_ok"] = False
        out["api_key_error"] = str(e)[:200]
    return out


@tool(S)
async def homarr_api_paths(contains: Optional[str] = None) -> Any:
    """List the REST endpoints of this Homarr instance (from its OpenAPI spec) so you know what homarr_api_request can call. Optional substring filter."""
    spec = await call(S, "GET", "/api/openapi", timeout=30)
    if not isinstance(spec, dict):
        raise ServiceError("Homarr did not return an OpenAPI document.")
    out = []
    for path, methods in (spec.get("paths") or {}).items():
        if contains and contains.lower() not in path.lower():
            continue
        for m, d in methods.items():
            if isinstance(d, dict):
                out.append({"method": m.upper(), "path": path, "summary": d.get("summary") or d.get("description", "")[:100]})
    return out


@tool(S)
async def homarr_list_boards() -> Any:
    """List Homarr boards (best effort: tries the REST endpoint, then tRPC)."""
    try:
        return redact(await call(S, "GET", "/api/boards", timeout=20))
    except ServiceError:
        d = await call(S, "GET", "/api/trpc/board.getAllBoards", timeout=20)
        try:
            data = d["result"]["data"]
            return redact(data.get("json", data))
        except Exception:
            return redact(d)


@tool(S, "write", mixed=True)
async def homarr_api_request(method: str, path: str, query: Optional[dict] = None, body: Optional[Any] = None) -> Any:
    """Raw Homarr API request, e.g. GET '/api/boards/<id>' or PUT '/api/boards/<id>/content'. Use homarr_api_paths to discover endpoints. GET only in read-only mode."""
    return await generic(S, method, path, query, body)
