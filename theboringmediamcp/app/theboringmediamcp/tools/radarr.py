"""Radarr tools (API v3)."""

import datetime as dt
from typing import Any, Optional

from ..core import ServiceError, call, generic, page, pick, ping, tool

S = "radarr"
A = "/api/v3"
MOVIE_KEYS = ["id", "title", "year", "tmdbId", "imdbId", "status", "monitored", "hasFile",
              "sizeOnDisk", "qualityProfileId", "path", "added", "minimumAvailability"]


@ping(S)
async def _ping(cfg: dict) -> dict:
    d = await call(S, "GET", f"{A}/system/status", cfg_override=cfg)
    return {"version": d.get("version"), "detail": d.get("appName", "Radarr")}


@tool(S)
async def radarr_status() -> Any:
    """Radarr version and health warnings."""
    st = await call(S, "GET", f"{A}/system/status")
    health = await call(S, "GET", f"{A}/health")
    return {**pick(st, ["appName", "version", "branch", "startTime", "osName", "isDocker"]),
            "health": pick(health, ["source", "type", "message"])}


@tool(S)
async def radarr_list_movies(search: Optional[str] = None, monitored: Optional[bool] = None,
                             has_file: Optional[bool] = None, limit: int = 50, offset: int = 0) -> Any:
    """List movies in the Radarr library, optionally filtered by title text / monitored / has_file."""
    movies = await call(S, "GET", f"{A}/movie")
    if search:
        movies = [m for m in movies if search.lower() in (m.get("title") or "").lower()]
    if monitored is not None:
        movies = [m for m in movies if bool(m.get("monitored")) == monitored]
    if has_file is not None:
        movies = [m for m in movies if bool(m.get("hasFile")) == has_file]
    return page(pick(movies, MOVIE_KEYS), limit, offset)


@tool(S)
async def radarr_get_movie(movie_id: int) -> Any:
    """Full details of one movie in the library, including file info."""
    m = await call(S, "GET", f"{A}/movie/{movie_id}")
    m.pop("images", None)
    return m


@tool(S)
async def radarr_lookup(term: str) -> Any:
    """Search TMDb through Radarr. term can be a title, 'tmdb:603' or 'imdb:tt0133093'. 'id' is set if already in the library."""
    r = await call(S, "GET", f"{A}/movie/lookup", params={"term": term})
    out = pick(r, ["id", "title", "year", "tmdbId", "imdbId", "overview", "runtime", "studio", "status"])
    for o in out:
        if o.get("overview"):
            o["overview"] = o["overview"][:300]
    return out[:15]


async def _defaults(profile_id: Optional[int], root: Optional[str]) -> tuple[int, str]:
    if profile_id is None:
        profiles = await call(S, "GET", f"{A}/qualityprofile")
        if not profiles:
            raise ServiceError("No quality profile configured in Radarr.")
        profile_id = profiles[0]["id"]
    if not root:
        roots = await call(S, "GET", f"{A}/rootfolder")
        if not roots:
            raise ServiceError("No root folder configured in Radarr.")
        root = roots[0]["path"]
    return profile_id, root


@tool(S, "write")
async def radarr_add_movie(tmdb_id: int, quality_profile_id: Optional[int] = None,
                           root_folder_path: Optional[str] = None, monitored: bool = True,
                           search_now: bool = True, minimum_availability: str = "released",
                           tags: Optional[list[int]] = None) -> Any:
    """Add a movie by TMDb id. Defaults: first quality profile and first root folder (see radarr_quality_profiles / radarr_root_folders). minimum_availability: announced | inCinemas | released."""
    found = await call(S, "GET", f"{A}/movie/lookup", params={"term": f"tmdb:{tmdb_id}"})
    if not found:
        raise ServiceError(f"TMDb id {tmdb_id} not found.")
    movie = found[0]
    if movie.get("id"):
        raise ServiceError(f"'{movie.get('title')}' is already in the library (id {movie['id']}).")
    pid, root = await _defaults(quality_profile_id, root_folder_path)
    movie.update({"qualityProfileId": pid, "rootFolderPath": root, "monitored": monitored,
                  "minimumAvailability": minimum_availability, "tags": tags or [],
                  "addOptions": {"searchForMovie": search_now}})
    added = await call(S, "POST", f"{A}/movie", body=movie)
    return pick(added, MOVIE_KEYS)


@tool(S, "write")
async def radarr_update_movie(movie_id: int, monitored: Optional[bool] = None,
                              quality_profile_id: Optional[int] = None,
                              minimum_availability: Optional[str] = None,
                              tags: Optional[list[int]] = None) -> Any:
    """Change monitored flag, quality profile, minimum availability or tags of a library movie."""
    m = await call(S, "GET", f"{A}/movie/{movie_id}")
    if monitored is not None:
        m["monitored"] = monitored
    if quality_profile_id is not None:
        m["qualityProfileId"] = quality_profile_id
    if minimum_availability is not None:
        m["minimumAvailability"] = minimum_availability
    if tags is not None:
        m["tags"] = tags
    return pick(await call(S, "PUT", f"{A}/movie/{movie_id}", body=m), MOVIE_KEYS)


@tool(S, "destructive")
async def radarr_delete_movie(movie_id: int, delete_files: bool = False, add_import_exclusion: bool = False) -> Any:
    """Remove a movie from Radarr. delete_files=True also deletes the files from disk."""
    return await call(S, "DELETE", f"{A}/movie/{movie_id}", params={
        "deleteFiles": str(delete_files).lower(), "addImportExclusion": str(add_import_exclusion).lower()})


@tool(S)
async def radarr_queue(page_size: int = 50) -> Any:
    """Current download queue."""
    d = await call(S, "GET", f"{A}/queue", params={"page": 1, "pageSize": max(1, min(page_size, 200)),
                                                   "includeMovie": "true"})
    out = []
    for r in d.get("records", []):
        out.append({"id": r.get("id"), "movie": (r.get("movie") or {}).get("title"), "movieId": r.get("movieId"),
                    "title": r.get("title"), "status": r.get("status"),
                    "state": r.get("trackedDownloadState"), "size": r.get("size"), "sizeleft": r.get("sizeleft"),
                    "timeleft": r.get("timeleft"), "protocol": r.get("protocol"),
                    "client": r.get("downloadClient"), "error": r.get("errorMessage"),
                    "messages": [m.get("title") for m in r.get("statusMessages", [])][:3]})
    return {"total": d.get("totalRecords"), "items": out}


@tool(S, "destructive")
async def radarr_remove_queue_item(queue_id: int, remove_from_client: bool = True, blocklist: bool = False) -> Any:
    """Remove an item from the queue (optionally also from the download client and add to blocklist)."""
    return await call(S, "DELETE", f"{A}/queue/{queue_id}", params={
        "removeFromClient": str(remove_from_client).lower(), "blocklist": str(blocklist).lower()})


@tool(S)
async def radarr_calendar(start: Optional[str] = None, end: Optional[str] = None, unmonitored: bool = False) -> Any:
    """Upcoming releases. Dates as YYYY-MM-DD; default today … +30 days."""
    today = dt.date.today()
    d = await call(S, "GET", f"{A}/calendar", params={
        "start": start or today.isoformat(), "end": end or (today + dt.timedelta(days=30)).isoformat(),
        "unmonitored": str(unmonitored).lower()})
    return pick(d, ["id", "title", "year", "inCinemas", "digitalRelease", "physicalRelease", "monitored", "hasFile"])


@tool(S)
async def radarr_history(page_size: int = 30, movie_id: Optional[int] = None) -> Any:
    """Recent history (grabs, imports, failures). Optionally for one movie."""
    if movie_id:
        d = await call(S, "GET", f"{A}/history/movie", params={"movieId": movie_id})
        recs = d
    else:
        d = await call(S, "GET", f"{A}/history", params={
            "page": 1, "pageSize": max(1, min(page_size, 200)), "sortKey": "date", "sortDirection": "descending"})
        recs = d.get("records", [])
    return pick(recs, ["id", "movieId", "sourceTitle", "eventType", "date", "quality", "data"])


@tool(S)
async def radarr_wanted_missing(page_size: int = 30) -> Any:
    """Monitored movies that have no file yet."""
    d = await call(S, "GET", f"{A}/wanted/missing", params={"page": 1, "pageSize": max(1, min(page_size, 200)),
                                                            "monitored": "true"})
    return {"total": d.get("totalRecords"), "items": pick(d.get("records", []), MOVIE_KEYS)}


@tool(S, "write")
async def radarr_search_movies(movie_ids: list[int]) -> Any:
    """Trigger an automatic search for the given library movie ids."""
    return await call(S, "POST", f"{A}/command", body={"name": "MoviesSearch", "movieIds": movie_ids})


@tool(S, "write")
async def radarr_command(name: str, params: Optional[dict] = None) -> Any:
    """Run a Radarr command, e.g. RefreshMovie, RescanMovie, RssSync, MissingMoviesSearch, DownloadedMoviesScan, RenameFiles, Backup. params are merged into the command body (e.g. {"movieIds":[1]})."""
    return await call(S, "POST", f"{A}/command", body={"name": name, **(params or {})})


@tool(S)
async def radarr_get_releases(movie_id: int) -> Any:
    """Interactive search: list available releases for a movie (can take a while)."""
    d = await call(S, "GET", f"{A}/release", params={"movieId": movie_id}, timeout=120)
    out = []
    for r in d[:60]:
        out.append({"guid": r.get("guid"), "indexerId": r.get("indexerId"), "title": r.get("title"),
                    "size": r.get("size"), "quality": ((r.get("quality") or {}).get("quality") or {}).get("name"),
                    "seeders": r.get("seeders"), "protocol": r.get("protocol"), "ageHours": r.get("ageHours"),
                    "approved": not r.get("rejected"), "rejections": (r.get("rejections") or [])[:2]})
    return out


@tool(S, "write")
async def radarr_grab_release(guid: str, indexer_id: int) -> Any:
    """Download a specific release found with radarr_get_releases."""
    return await call(S, "POST", f"{A}/release", body={"guid": guid, "indexerId": indexer_id})


@tool(S)
async def radarr_quality_profiles() -> Any:
    """Quality profiles (id + name)."""
    return pick(await call(S, "GET", f"{A}/qualityprofile"), ["id", "name", "upgradeAllowed"])


@tool(S)
async def radarr_root_folders() -> Any:
    """Root folders with free space."""
    return pick(await call(S, "GET", f"{A}/rootfolder"), ["id", "path", "accessible", "freeSpace"])


@tool(S)
async def radarr_disk_space() -> Any:
    """Disk space of all drives Radarr knows."""
    return pick(await call(S, "GET", f"{A}/diskspace"), ["path", "label", "freeSpace", "totalSpace"])


@tool(S, "write", mixed=True)
async def radarr_api_request(method: str, path: str, query: Optional[dict] = None, body: Optional[Any] = None) -> Any:
    """Raw Radarr API request. path starts with '/', e.g. '/api/v3/tag'. GET only in read-only mode."""
    return await generic(S, method, path, query, body)
