"""Seerr tools (Seerr / Jellyseerr / Overseerr, API v1)."""

from typing import Any, Optional
from urllib.parse import quote

from ..core import ServiceError, call, generic, pick, ping, tool

S = "seerr"
A = "/api/v1"
MEDIA_STATUS = {1: "unknown", 2: "pending", 3: "processing", 4: "partially_available", 5: "available"}


@ping(S)
async def _ping(cfg: dict) -> dict:
    d = await call(S, "GET", f"{A}/status", cfg_override=cfg)
    # /status is public; /auth/me proves the key works
    me = await call(S, "GET", f"{A}/auth/me", cfg_override=cfg)
    return {"version": d.get("version"), "detail": f"authenticated as {me.get('displayName') or me.get('email')}"}


def _slim_media(r: dict) -> dict:
    mi = r.get("mediaInfo") or {}
    return {"id": r.get("id"), "mediaType": r.get("mediaType"),
            "title": r.get("title") or r.get("name"),
            "date": r.get("releaseDate") or r.get("firstAirDate"),
            "overview": (r.get("overview") or "")[:200],
            "status": MEDIA_STATUS.get(mi.get("status"), "not_requested") if mi else "not_requested"}


@tool(S)
async def seerr_status() -> Any:
    """Seerr version and update state."""
    return await call(S, "GET", f"{A}/status")


@tool(S)
async def seerr_search(query: str, page: int = 1) -> Any:
    """Search movies and series (TMDb). 'status' tells whether it is already requested/available. Use 'id' (TMDb id) with seerr_create_request."""
    d = await call(S, "GET", f"{A}/search?query={quote(query)}&page={page}")
    return {"totalResults": d.get("totalResults"),
            "results": [_slim_media(r) for r in d.get("results", []) if r.get("mediaType") in ("movie", "tv")]}


@tool(S)
async def seerr_discover(kind: str = "trending", page: int = 1) -> Any:
    """Discover media. kind: trending | movies | tv | upcoming_movies | upcoming_tv."""
    paths = {"trending": "/discover/trending", "movies": "/discover/movies", "tv": "/discover/tv",
             "upcoming_movies": "/discover/movies/upcoming", "upcoming_tv": "/discover/tv/upcoming"}
    if kind not in paths:
        raise ServiceError(f"kind must be one of {', '.join(paths)}")
    d = await call(S, "GET", f"{A}{paths[kind]}", params={"page": page})
    return [_slim_media({**r, "mediaType": r.get("mediaType") or ("movie" if "movies" in kind else "tv")})
            for r in d.get("results", [])]


@tool(S)
async def seerr_movie_details(tmdb_id: int) -> Any:
    """Movie details (overview, genres, runtime, availability)."""
    d = await call(S, "GET", f"{A}/movie/{tmdb_id}")
    out = pick(d, ["id", "title", "releaseDate", "runtime", "overview", "tagline", "voteAverage", "status"])
    out["genres"] = [g.get("name") for g in d.get("genres", [])]
    out["availability"] = MEDIA_STATUS.get((d.get("mediaInfo") or {}).get("status"), "not_requested")
    return out


@tool(S)
async def seerr_tv_details(tmdb_id: int) -> Any:
    """Series details incl. seasons and availability."""
    d = await call(S, "GET", f"{A}/tv/{tmdb_id}")
    out = pick(d, ["id", "name", "firstAirDate", "overview", "numberOfSeasons", "numberOfEpisodes", "status", "voteAverage"])
    out["genres"] = [g.get("name") for g in d.get("genres", [])]
    out["seasons"] = pick(d.get("seasons", []), ["seasonNumber", "episodeCount", "name"])
    out["availability"] = MEDIA_STATUS.get((d.get("mediaInfo") or {}).get("status"), "not_requested")
    return out


@tool(S)
async def seerr_list_requests(filter: str = "all", take: int = 20, skip: int = 0, sort: str = "added") -> Any:
    """List requests. filter: all | pending | approved | processing | available | unavailable | failed | deleted. sort: added | modified."""
    d = await call(S, "GET", f"{A}/request", params={"filter": filter, "take": max(1, min(take, 100)),
                                                     "skip": skip, "sort": sort})
    out = []
    for r in d.get("results", []):
        media = r.get("media") or {}
        out.append({"id": r.get("id"), "status": {1: "pending", 2: "approved", 3: "declined"}.get(r.get("status")),
                    "type": r.get("type"), "tmdbId": media.get("tmdbId"), "is4k": r.get("is4k"),
                    "requestedBy": (r.get("requestedBy") or {}).get("displayName"),
                    "createdAt": r.get("createdAt"), "seasons": [s.get("seasonNumber") for s in r.get("seasons", [])],
                    "mediaStatus": MEDIA_STATUS.get(media.get("status"))})
    return {"total": (d.get("pageInfo") or {}).get("results"), "items": out}


@tool(S)
async def seerr_request_counts() -> Any:
    """Number of requests per state."""
    return await call(S, "GET", f"{A}/request/count")


@tool(S)
async def seerr_get_request(request_id: int) -> Any:
    """One request in detail."""
    return await call(S, "GET", f"{A}/request/{request_id}")


@tool(S, "write")
async def seerr_create_request(media_type: str, tmdb_id: int, seasons: Optional[list[int]] = None,
                               is4k: bool = False) -> Any:
    """Request a movie or series. media_type: movie | tv. For tv leave seasons empty to request all seasons, or pass season numbers."""
    if media_type not in ("movie", "tv"):
        raise ServiceError("media_type must be 'movie' or 'tv'")
    body: dict = {"mediaType": media_type, "mediaId": tmdb_id, "is4k": is4k}
    if media_type == "tv":
        body["seasons"] = seasons if seasons else "all"
    return pick(await call(S, "POST", f"{A}/request", body=body), ["id", "status", "type", "createdAt"])


@tool(S, "write")
async def seerr_approve_request(request_id: int) -> Any:
    """Approve a pending request."""
    return pick(await call(S, "POST", f"{A}/request/{request_id}/approve"), ["id", "status", "type"])


@tool(S, "write")
async def seerr_decline_request(request_id: int) -> Any:
    """Decline a pending request."""
    return pick(await call(S, "POST", f"{A}/request/{request_id}/decline"), ["id", "status", "type"])


@tool(S, "destructive")
async def seerr_delete_request(request_id: int) -> Any:
    """Delete a request."""
    return await call(S, "DELETE", f"{A}/request/{request_id}")


@tool(S)
async def seerr_list_issues(take: int = 20, filter: str = "open") -> Any:
    """Reported issues. filter: all | open | resolved."""
    d = await call(S, "GET", f"{A}/issue", params={"take": max(1, min(take, 100)), "filter": filter})
    return pick(d.get("results", []), ["id", "issueType", "status", "createdAt", "message"])


@tool(S)
async def seerr_list_users(take: int = 50) -> Any:
    """Seerr users."""
    d = await call(S, "GET", f"{A}/user", params={"take": max(1, min(take, 200))})
    return pick(d.get("results", []), ["id", "displayName", "email", "requestCount", "permissions"])


@tool(S, "write", mixed=True)
async def seerr_api_request(method: str, path: str, query: Optional[dict] = None, body: Optional[Any] = None) -> Any:
    """Raw Seerr API request. path starts with '/', e.g. '/api/v1/settings/main'. GET only in read-only mode."""
    return await generic(S, method, path, query, body)
