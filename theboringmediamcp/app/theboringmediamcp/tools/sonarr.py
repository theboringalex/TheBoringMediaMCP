"""Sonarr tools (API v3)."""

import datetime as dt
from typing import Any, Optional

from ..core import ServiceError, call, generic, page, pick, ping, tool

S = "sonarr"
A = "/api/v3"
SERIES_KEYS = ["id", "title", "year", "tvdbId", "imdbId", "status", "monitored", "seriesType",
               "qualityProfileId", "path", "added", "network"]


@ping(S)
async def _ping(cfg: dict) -> dict:
    d = await call(S, "GET", f"{A}/system/status", cfg_override=cfg)
    return {"version": d.get("version"), "detail": d.get("appName", "Sonarr")}


def _stats(s: dict) -> dict:
    st = s.get("statistics") or {}
    out = pick(s, SERIES_KEYS)
    out.update({"seasons": st.get("seasonCount"), "episodes": f"{st.get('episodeFileCount')}/{st.get('episodeCount')}",
                "sizeOnDisk": st.get("sizeOnDisk")})
    return out


@tool(S)
async def sonarr_status() -> Any:
    """Sonarr version and health warnings."""
    st = await call(S, "GET", f"{A}/system/status")
    health = await call(S, "GET", f"{A}/health")
    return {**pick(st, ["appName", "version", "branch", "startTime", "osName", "isDocker"]),
            "health": pick(health, ["source", "type", "message"])}


@tool(S)
async def sonarr_list_series(search: Optional[str] = None, monitored: Optional[bool] = None,
                             limit: int = 50, offset: int = 0) -> Any:
    """List series in the Sonarr library (with episode counts)."""
    series = await call(S, "GET", f"{A}/series")
    if search:
        series = [s for s in series if search.lower() in (s.get("title") or "").lower()]
    if monitored is not None:
        series = [s for s in series if bool(s.get("monitored")) == monitored]
    p = page(series, limit, offset)
    p["items"] = [_stats(s) for s in p["items"]]
    return p


@tool(S)
async def sonarr_get_series(series_id: int) -> Any:
    """Full details of one series including seasons."""
    s = await call(S, "GET", f"{A}/series/{series_id}")
    s.pop("images", None)
    return s


@tool(S)
async def sonarr_lookup(term: str) -> Any:
    """Search TheTVDB through Sonarr. term can be a title or 'tvdb:81189'. 'id' is set if already in the library."""
    r = await call(S, "GET", f"{A}/series/lookup", params={"term": term})
    out = pick(r, ["id", "title", "year", "tvdbId", "imdbId", "overview", "network", "status", "seasonCount"])
    for o in out:
        if o.get("overview"):
            o["overview"] = o["overview"][:300]
    return out[:15]


@tool(S, "write")
async def sonarr_add_series(tvdb_id: int, quality_profile_id: Optional[int] = None,
                            root_folder_path: Optional[str] = None, monitor: str = "all",
                            series_type: str = "standard", season_folder: bool = True,
                            search_missing: bool = True, tags: Optional[list[int]] = None) -> Any:
    """Add a series by TVDB id. monitor: all | future | missing | existing | firstSeason | lastSeason | pilot | none. series_type: standard | daily | anime."""
    found = await call(S, "GET", f"{A}/series/lookup", params={"term": f"tvdb:{tvdb_id}"})
    if not found:
        raise ServiceError(f"TVDB id {tvdb_id} not found.")
    series = found[0]
    if series.get("id"):
        raise ServiceError(f"'{series.get('title')}' is already in the library (id {series['id']}).")
    if quality_profile_id is None:
        profiles = await call(S, "GET", f"{A}/qualityprofile")
        if not profiles:
            raise ServiceError("No quality profile configured in Sonarr.")
        quality_profile_id = profiles[0]["id"]
    if not root_folder_path:
        roots = await call(S, "GET", f"{A}/rootfolder")
        if not roots:
            raise ServiceError("No root folder configured in Sonarr.")
        root_folder_path = roots[0]["path"]
    series.update({"qualityProfileId": quality_profile_id, "rootFolderPath": root_folder_path,
                   "monitored": monitor != "none", "seriesType": series_type, "seasonFolder": season_folder,
                   "tags": tags or [],
                   "addOptions": {"monitor": monitor, "searchForMissingEpisodes": search_missing,
                                  "searchForCutoffUnmetEpisodes": False}})
    return _stats(await call(S, "POST", f"{A}/series", body=series))


@tool(S, "write")
async def sonarr_update_series(series_id: int, monitored: Optional[bool] = None,
                               quality_profile_id: Optional[int] = None, series_type: Optional[str] = None,
                               season_folder: Optional[bool] = None, tags: Optional[list[int]] = None) -> Any:
    """Change monitored flag, quality profile, series type, season folders or tags."""
    s = await call(S, "GET", f"{A}/series/{series_id}")
    for k, v in (("monitored", monitored), ("qualityProfileId", quality_profile_id), ("seriesType", series_type),
                 ("seasonFolder", season_folder), ("tags", tags)):
        if v is not None:
            s[k] = v
    return _stats(await call(S, "PUT", f"{A}/series/{series_id}", body=s))


@tool(S, "destructive")
async def sonarr_delete_series(series_id: int, delete_files: bool = False, add_import_list_exclusion: bool = False) -> Any:
    """Remove a series from Sonarr. delete_files=True also deletes the files from disk."""
    return await call(S, "DELETE", f"{A}/series/{series_id}", params={
        "deleteFiles": str(delete_files).lower(), "addImportListExclusion": str(add_import_list_exclusion).lower()})


@tool(S)
async def sonarr_episodes(series_id: int, season_number: Optional[int] = None) -> Any:
    """Episodes of a series (optionally one season) with file/monitor status."""
    eps = await call(S, "GET", f"{A}/episode", params={"seriesId": series_id, "seasonNumber": season_number})
    return pick(eps, ["id", "seasonNumber", "episodeNumber", "title", "airDate", "monitored", "hasFile"])


@tool(S, "write")
async def sonarr_set_episodes_monitored(episode_ids: list[int], monitored: bool) -> Any:
    """Monitor or unmonitor episodes."""
    return await call(S, "PUT", f"{A}/episode/monitor", body={"episodeIds": episode_ids, "monitored": monitored})


@tool(S)
async def sonarr_queue(page_size: int = 50) -> Any:
    """Current download queue."""
    d = await call(S, "GET", f"{A}/queue", params={"page": 1, "pageSize": max(1, min(page_size, 200)),
                                                   "includeSeries": "true", "includeEpisode": "true"})
    out = []
    for r in d.get("records", []):
        ep = r.get("episode") or {}
        out.append({"id": r.get("id"), "series": (r.get("series") or {}).get("title"),
                    "episode": f"S{ep.get('seasonNumber', 0):02d}E{ep.get('episodeNumber', 0):02d}" if ep else None,
                    "title": r.get("title"), "status": r.get("status"), "state": r.get("trackedDownloadState"),
                    "size": r.get("size"), "sizeleft": r.get("sizeleft"), "timeleft": r.get("timeleft"),
                    "protocol": r.get("protocol"), "client": r.get("downloadClient"),
                    "error": r.get("errorMessage"),
                    "messages": [m.get("title") for m in r.get("statusMessages", [])][:3]})
    return {"total": d.get("totalRecords"), "items": out}


@tool(S, "destructive")
async def sonarr_remove_queue_item(queue_id: int, remove_from_client: bool = True, blocklist: bool = False) -> Any:
    """Remove an item from the queue (optionally also from the download client and add to blocklist)."""
    return await call(S, "DELETE", f"{A}/queue/{queue_id}", params={
        "removeFromClient": str(remove_from_client).lower(), "blocklist": str(blocklist).lower()})


@tool(S)
async def sonarr_calendar(start: Optional[str] = None, end: Optional[str] = None, unmonitored: bool = False) -> Any:
    """Upcoming episodes. Dates as YYYY-MM-DD; default today … +14 days."""
    today = dt.date.today()
    d = await call(S, "GET", f"{A}/calendar", params={
        "start": start or today.isoformat(), "end": end or (today + dt.timedelta(days=14)).isoformat(),
        "unmonitored": str(unmonitored).lower(), "includeSeries": "true"})
    return [{"id": e.get("id"), "series": (e.get("series") or {}).get("title"), "season": e.get("seasonNumber"),
             "episode": e.get("episodeNumber"), "title": e.get("title"), "airDateUtc": e.get("airDateUtc"),
             "hasFile": e.get("hasFile"), "monitored": e.get("monitored")} for e in d]


@tool(S)
async def sonarr_history(page_size: int = 30, series_id: Optional[int] = None) -> Any:
    """Recent history (grabs, imports, failures). Optionally for one series."""
    d = await call(S, "GET", f"{A}/history", params={
        "page": 1, "pageSize": max(1, min(page_size, 200)), "sortKey": "date", "sortDirection": "descending",
        "seriesIds": series_id})
    return pick(d.get("records", []), ["id", "seriesId", "episodeId", "sourceTitle", "eventType", "date", "quality"])


@tool(S)
async def sonarr_wanted_missing(page_size: int = 30) -> Any:
    """Monitored episodes that have no file yet."""
    d = await call(S, "GET", f"{A}/wanted/missing", params={"page": 1, "pageSize": max(1, min(page_size, 200)),
                                                            "monitored": "true", "includeSeries": "true"})
    return {"total": d.get("totalRecords"),
            "items": [{"id": e.get("id"), "series": (e.get("series") or {}).get("title"),
                       "season": e.get("seasonNumber"), "episode": e.get("episodeNumber"),
                       "title": e.get("title"), "airDate": e.get("airDate")} for e in d.get("records", [])]}


@tool(S, "write")
async def sonarr_search(series_id: Optional[int] = None, season_number: Optional[int] = None,
                        episode_ids: Optional[list[int]] = None) -> Any:
    """Trigger an automatic search: whole series (series_id), one season (series_id + season_number) or specific episodes (episode_ids)."""
    if episode_ids:
        body = {"name": "EpisodeSearch", "episodeIds": episode_ids}
    elif series_id is not None and season_number is not None:
        body = {"name": "SeasonSearch", "seriesId": series_id, "seasonNumber": season_number}
    elif series_id is not None:
        body = {"name": "SeriesSearch", "seriesId": series_id}
    else:
        raise ServiceError("Give series_id, series_id+season_number or episode_ids.")
    return await call(S, "POST", f"{A}/command", body=body)


@tool(S, "write")
async def sonarr_command(name: str, params: Optional[dict] = None) -> Any:
    """Run a Sonarr command, e.g. RefreshSeries, RescanSeries, RssSync, MissingEpisodeSearch, DownloadedEpisodesScan, RenameFiles, Backup. params are merged into the body (e.g. {"seriesId":1})."""
    return await call(S, "POST", f"{A}/command", body={"name": name, **(params or {})})


@tool(S)
async def sonarr_get_releases(episode_id: Optional[int] = None, series_id: Optional[int] = None,
                              season_number: Optional[int] = None) -> Any:
    """Interactive search: releases for an episode, or a season pack (series_id + season_number). Can take a while."""
    if episode_id is None and series_id is None:
        raise ServiceError("Give episode_id or series_id (+ season_number).")
    d = await call(S, "GET", f"{A}/release", params={"episodeId": episode_id, "seriesId": series_id,
                                                      "seasonNumber": season_number}, timeout=120)
    return [{"guid": r.get("guid"), "indexerId": r.get("indexerId"), "title": r.get("title"),
             "size": r.get("size"), "quality": ((r.get("quality") or {}).get("quality") or {}).get("name"),
             "seeders": r.get("seeders"), "protocol": r.get("protocol"), "ageHours": r.get("ageHours"),
             "fullSeason": r.get("fullSeason"), "approved": not r.get("rejected"),
             "rejections": (r.get("rejections") or [])[:2]} for r in d[:60]]


@tool(S, "write")
async def sonarr_grab_release(guid: str, indexer_id: int) -> Any:
    """Download a specific release found with sonarr_get_releases."""
    return await call(S, "POST", f"{A}/release", body={"guid": guid, "indexerId": indexer_id})


@tool(S)
async def sonarr_quality_profiles() -> Any:
    """Quality profiles (id + name)."""
    return pick(await call(S, "GET", f"{A}/qualityprofile"), ["id", "name", "upgradeAllowed"])


@tool(S)
async def sonarr_root_folders() -> Any:
    """Root folders with free space."""
    return pick(await call(S, "GET", f"{A}/rootfolder"), ["id", "path", "accessible", "freeSpace"])


@tool(S)
async def sonarr_disk_space() -> Any:
    """Disk space of all drives Sonarr knows."""
    return pick(await call(S, "GET", f"{A}/diskspace"), ["path", "label", "freeSpace", "totalSpace"])


@tool(S, "write", mixed=True)
async def sonarr_api_request(method: str, path: str, query: Optional[dict] = None, body: Optional[Any] = None) -> Any:
    """Raw Sonarr API request. path starts with '/', e.g. '/api/v3/tag'. GET only in read-only mode."""
    return await generic(S, method, path, query, body)
