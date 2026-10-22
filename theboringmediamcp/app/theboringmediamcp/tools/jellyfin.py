"""Jellyfin tools."""

from typing import Any, Optional

from ..core import call, generic, ping, pick, tool

S = "jellyfin"
ITEM_KEYS = ["Id", "Name", "Type", "ProductionYear", "CommunityRating", "OfficialRating",
             "Path", "DateCreated", "RunTimeTicks", "SeriesName", "ParentIndexNumber",
             "IndexNumber", "IsFolder", "ChildCount"]


def _ids(item_ids: list[str]) -> str:
    return ",".join(i.strip() for i in item_ids if i and i.strip())


@ping(S)
async def _ping(cfg: dict) -> dict:
    info = await call(S, "GET", "/System/Info", cfg_override=cfg)
    return {"version": info.get("Version"), "detail": f"{info.get('ServerName')} · {info.get('OperatingSystem', '')}"}


@tool(S)
async def jellyfin_system_info() -> Any:
    """Jellyfin server name, version, OS, address and whether a restart/update is pending."""
    d = await call(S, "GET", "/System/Info")
    return pick(d, ["ServerName", "Version", "OperatingSystem", "LocalAddress", "Id",
                    "HasPendingRestart", "HasUpdateAvailable", "ProductName"])


@tool(S)
async def jellyfin_list_libraries() -> Any:
    """List all Jellyfin libraries (name, type, id, folders)."""
    d = await call(S, "GET", "/Library/VirtualFolders")
    return pick(d, ["Name", "CollectionType", "ItemId", "Locations", "RefreshStatus"])


@tool(S)
async def jellyfin_list_users() -> Any:
    """List Jellyfin users (id, name, admin flag, last activity)."""
    d = await call(S, "GET", "/Users")
    return [{"Id": u.get("Id"), "Name": u.get("Name"), "LastActivityDate": u.get("LastActivityDate"),
             "IsAdministrator": (u.get("Policy") or {}).get("IsAdministrator"),
             "IsDisabled": (u.get("Policy") or {}).get("IsDisabled")} for u in d]


@tool(S)
async def jellyfin_search(query: str, item_types: str = "Movie,Series,Episode,BoxSet", limit: int = 20) -> Any:
    """Search the Jellyfin library by text. item_types is a comma list (Movie, Series, Episode, Season, BoxSet, Audio, MusicAlbum, Person)."""
    d = await call(S, "GET", "/Items", params={
        "searchTerm": query, "Recursive": "true", "IncludeItemTypes": item_types,
        "Limit": max(1, min(limit, 100)), "Fields": "Path,DateCreated,ProductionYear"})
    return {"total": d.get("TotalRecordCount"), "items": pick(d.get("Items", []), ITEM_KEYS)}


@tool(S)
async def jellyfin_browse(parent_id: Optional[str] = None, item_types: Optional[str] = None,
                          sort_by: str = "SortName", sort_order: str = "Ascending",
                          limit: int = 50, start_index: int = 0, recursive: bool = False,
                          filters: Optional[str] = None, search_genre: Optional[str] = None) -> Any:
    """Browse Jellyfin items. parent_id = library/folder/collection id. filters e.g. 'IsUnplayed,IsFavorite'. sort_by e.g. SortName, DateCreated, PremiereDate, CommunityRating."""
    d = await call(S, "GET", "/Items", params={
        "ParentId": parent_id, "IncludeItemTypes": item_types, "SortBy": sort_by,
        "SortOrder": sort_order, "Limit": max(1, min(limit, 200)), "StartIndex": start_index,
        "Recursive": str(recursive).lower(), "Filters": filters, "Genres": search_genre,
        "Fields": "Path,DateCreated,ProductionYear"})
    return {"total": d.get("TotalRecordCount"), "start": start_index, "items": pick(d.get("Items", []), ITEM_KEYS)}


@tool(S)
async def jellyfin_latest(item_types: str = "Movie,Series", limit: int = 20) -> Any:
    """Most recently added items."""
    d = await call(S, "GET", "/Items", params={
        "Recursive": "true", "IncludeItemTypes": item_types, "SortBy": "DateCreated",
        "SortOrder": "Descending", "Limit": max(1, min(limit, 100)),
        "Fields": "Path,DateCreated,ProductionYear"})
    return pick(d.get("Items", []), ITEM_KEYS)


@tool(S)
async def jellyfin_get_item(item_id: str) -> Any:
    """Full details of one item (overview, genres, provider ids, media streams)."""
    d = await call(S, "GET", "/Items", params={
        "Ids": item_id, "Fields": "Overview,Genres,ProviderIds,Path,DateCreated,MediaSources,Tags,Studios,Taglines"})
    items = d.get("Items", [])
    if not items:
        return {"error": f"No item with id {item_id}"}
    it = items[0]
    for ms in it.get("MediaSources", []) or []:
        ms.pop("MediaStreams", None)
    return it


@tool(S)
async def jellyfin_sessions(active_only: bool = True) -> Any:
    """Current client sessions and what is playing."""
    d = await call(S, "GET", "/Sessions", params={"ActiveWithinSeconds": 960 if active_only else None})
    out = []
    for s in d:
        np = s.get("NowPlayingItem") or {}
        out.append({"Id": s.get("Id"), "User": s.get("UserName"), "Client": s.get("Client"),
                    "Device": s.get("DeviceName"), "LastActivity": s.get("LastActivityDate"),
                    "NowPlaying": np.get("Name"), "Paused": (s.get("PlayState") or {}).get("IsPaused")})
    return out


@tool(S)
async def jellyfin_activity_log(limit: int = 30) -> Any:
    """Recent server activity (logins, playback, failures)."""
    d = await call(S, "GET", "/System/ActivityLog/Entries", params={"limit": max(1, min(limit, 200))})
    return pick(d.get("Items", []), ["Date", "Name", "ShortOverview", "Type", "Severity"])


@tool(S, "write")
async def jellyfin_library_scan() -> Any:
    """Start a scan of all libraries."""
    return await call(S, "POST", "/Library/Refresh")


@tool(S, "write")
async def jellyfin_refresh_item(item_id: str, replace_metadata: bool = False, replace_images: bool = False) -> Any:
    """Refresh metadata of one item (movie, series, library folder, collection)."""
    return await call(S, "POST", f"/Items/{item_id}/Refresh", params={
        "Recursive": "true",
        "MetadataRefreshMode": "FullRefresh" if replace_metadata else "Default",
        "ImageRefreshMode": "FullRefresh" if replace_images else "Default",
        "ReplaceAllMetadata": str(replace_metadata).lower(),
        "ReplaceAllImages": str(replace_images).lower()})


@tool(S)
async def jellyfin_scheduled_tasks() -> Any:
    """List scheduled tasks with state and last result."""
    d = await call(S, "GET", "/ScheduledTasks")
    return [{"Id": t.get("Id"), "Name": t.get("Name"), "Category": t.get("Category"), "State": t.get("State"),
             "Progress": t.get("CurrentProgressPercentage"),
             "LastResult": (t.get("LastExecutionResult") or {}).get("Status")} for t in d]


@tool(S, "write")
async def jellyfin_run_task(task_id: str) -> Any:
    """Start a scheduled task by id (see jellyfin_scheduled_tasks)."""
    return await call(S, "POST", f"/ScheduledTasks/Running/{task_id}")


@tool(S)
async def jellyfin_list_collections(limit: int = 100) -> Any:
    """List all collections (box sets)."""
    d = await call(S, "GET", "/Items", params={
        "Recursive": "true", "IncludeItemTypes": "BoxSet", "SortBy": "SortName",
        "Limit": max(1, min(limit, 500)), "Fields": "ChildCount,DateCreated"})
    return pick(d.get("Items", []), ["Id", "Name", "ChildCount", "DateCreated"])


@tool(S)
async def jellyfin_collection_items(collection_id: str) -> Any:
    """Items inside a collection."""
    d = await call(S, "GET", "/Items", params={"ParentId": collection_id, "Limit": 500,
                                               "Fields": "ProductionYear"})
    return pick(d.get("Items", []), ["Id", "Name", "Type", "ProductionYear"])


@tool(S, "write")
async def jellyfin_create_collection(name: str, item_ids: list[str]) -> Any:
    """Create a collection with the given item ids."""
    return await call(S, "POST", "/Collections", params={"name": name, "ids": _ids(item_ids)})


@tool(S, "write")
async def jellyfin_add_to_collection(collection_id: str, item_ids: list[str]) -> Any:
    """Add items to a collection."""
    return await call(S, "POST", f"/Collections/{collection_id}/Items", params={"ids": _ids(item_ids)})


@tool(S, "write")
async def jellyfin_remove_from_collection(collection_id: str, item_ids: list[str]) -> Any:
    """Remove items from a collection (the items themselves stay in the library)."""
    return await call(S, "DELETE", f"/Collections/{collection_id}/Items", params={"ids": _ids(item_ids)})


@tool(S, "destructive")
async def jellyfin_delete_item(item_id: str) -> Any:
    """DELETE an item and its files from disk. Cannot be undone."""
    return await call(S, "DELETE", f"/Items/{item_id}")


@tool(S, "destructive")
async def jellyfin_restart_server() -> Any:
    """Restart the Jellyfin server (interrupts all streams)."""
    return await call(S, "POST", "/System/Restart")


@tool(S, "write", mixed=True)
async def jellyfin_api_request(method: str, path: str, query: Optional[dict] = None, body: Optional[Any] = None) -> Any:
    """Raw Jellyfin API request for anything not covered by other tools. path starts with '/', e.g. '/Items/Filters'. GET only in read-only mode."""
    return await generic(S, method, path, query, body)
