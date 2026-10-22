"""Prowlarr tools (API v1)."""

from typing import Any, Optional

from ..core import call, generic, pick, ping, tool

S = "prowlarr"
A = "/api/v1"
IDX_KEYS = ["id", "name", "protocol", "privacy", "enable", "priority", "appProfileId", "implementation"]


@ping(S)
async def _ping(cfg: dict) -> dict:
    d = await call(S, "GET", f"{A}/system/status", cfg_override=cfg)
    return {"version": d.get("version"), "detail": d.get("appName", "Prowlarr")}


@tool(S)
async def prowlarr_status() -> Any:
    """Prowlarr version and health warnings."""
    st = await call(S, "GET", f"{A}/system/status")
    health = await call(S, "GET", f"{A}/health")
    return {**pick(st, ["appName", "version", "branch", "startTime", "isDocker"]),
            "health": pick(health, ["source", "type", "message"])}


@tool(S)
async def prowlarr_list_indexers() -> Any:
    """All configured indexers."""
    return pick(await call(S, "GET", f"{A}/indexer"), IDX_KEYS)


@tool(S)
async def prowlarr_indexer_status() -> Any:
    """Indexers that are currently disabled/failing, with failure time."""
    return await call(S, "GET", f"{A}/indexerstatus")


@tool(S, "write")
async def prowlarr_set_indexer_enabled(indexer_id: int, enabled: bool) -> Any:
    """Enable or disable one indexer."""
    idx = await call(S, "GET", f"{A}/indexer/{indexer_id}")
    idx["enable"] = enabled
    return pick(await call(S, "PUT", f"{A}/indexer/{indexer_id}", body=idx), IDX_KEYS)


@tool(S, "write")
async def prowlarr_test_indexer(indexer_id: int) -> Any:
    """Test one indexer (connection + auth)."""
    idx = await call(S, "GET", f"{A}/indexer/{indexer_id}")
    return await call(S, "POST", f"{A}/indexer/test", body=idx, timeout=90)


@tool(S, "write")
async def prowlarr_test_all_indexers() -> Any:
    """Test every indexer. Returns per-indexer validation failures (empty = all fine)."""
    d = await call(S, "POST", f"{A}/indexer/testall", timeout=180)
    return [{"id": r.get("id"), "isValid": r.get("isValid"),
             "errors": [e.get("errorMessage") for e in r.get("validationFailures", [])]} for r in d]


@tool(S)
async def prowlarr_search(query: str, search_type: str = "search", indexer_ids: Optional[list[int]] = None,
                          categories: Optional[list[int]] = None, limit: int = 25) -> Any:
    """Search all (or selected) indexers. search_type: search | tvsearch | movie | music | book. categories: newznab ids, e.g. 2000 movies, 5000 TV."""
    params: dict = {"query": query, "type": search_type, "limit": max(1, min(limit, 100)), "offset": 0}
    if indexer_ids:
        params["indexerIds"] = indexer_ids
    if categories:
        params["categories"] = categories
    d = await call(S, "GET", f"{A}/search", params=params, timeout=120)
    return [{"guid": r.get("guid"), "indexerId": r.get("indexerId"), "indexer": r.get("indexer"),
             "title": r.get("title"), "size": r.get("size"), "seeders": r.get("seeders"),
             "leechers": r.get("leechers"), "protocol": r.get("protocol"), "age": r.get("age"),
             "categories": [c.get("name") for c in r.get("categories", [])][:3]} for r in d]


@tool(S, "write")
async def prowlarr_grab_release(guid: str, indexer_id: int) -> Any:
    """Send a release found with prowlarr_search to the default download client."""
    return await call(S, "POST", f"{A}/search", body={"guid": guid, "indexerId": indexer_id})


@tool(S)
async def prowlarr_applications() -> Any:
    """Connected apps (Radarr/Sonarr/…) and their sync level."""
    return pick(await call(S, "GET", f"{A}/applications"), ["id", "name", "syncLevel", "implementation"])


@tool(S)
async def prowlarr_indexer_stats() -> Any:
    """Per-indexer statistics (queries, grabs, failures, response times)."""
    d = await call(S, "GET", f"{A}/indexerstats")
    return pick(d.get("indexers", []), ["indexerId", "indexerName", "averageResponseTime", "numberOfQueries",
                                        "numberOfGrabs", "numberOfFailedQueries", "numberOfFailedGrabs"])


@tool(S)
async def prowlarr_history(page_size: int = 30) -> Any:
    """Recent search/grab history."""
    d = await call(S, "GET", f"{A}/history", params={"page": 1, "pageSize": max(1, min(page_size, 200)),
                                                     "sortKey": "date", "sortDirection": "descending"})
    return pick(d.get("records", []), ["id", "indexerId", "eventType", "date", "successful", "data"])


@tool(S, "destructive")
async def prowlarr_delete_indexer(indexer_id: int) -> Any:
    """Delete an indexer from Prowlarr."""
    return await call(S, "DELETE", f"{A}/indexer/{indexer_id}")


@tool(S, "write")
async def prowlarr_command(name: str, params: Optional[dict] = None) -> Any:
    """Run a Prowlarr command, e.g. ApplicationIndexerSync, CheckHealth, Backup."""
    return await call(S, "POST", f"{A}/command", body={"name": name, **(params or {})})


@tool(S, "write", mixed=True)
async def prowlarr_api_request(method: str, path: str, query: Optional[dict] = None, body: Optional[Any] = None) -> Any:
    """Raw Prowlarr API request. path starts with '/', e.g. '/api/v1/tag'. GET only in read-only mode."""
    return await generic(S, method, path, query, body)
