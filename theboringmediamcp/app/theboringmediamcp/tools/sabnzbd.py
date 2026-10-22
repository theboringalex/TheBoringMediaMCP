"""SABnzbd tools."""

from typing import Any, Optional

from ..config import CONFIG
from ..core import ServiceError, call, pick, ping, redact, tool

S = "sabnzbd"
PRIO = {"force": 2, "high": 1, "normal": 0, "low": -1, "paused": -2, "stop": -4}
READ_MODES = {"queue", "history", "version", "qstatus", "status", "fullstatus", "get_config", "server_stats",
              "warnings", "get_cats", "get_scripts", "browse", "eval_sort", "translate", "auth", "queue_list"}


async def sab(mode: str, **params: Any) -> Any:
    p = {"mode": mode, "output": "json"}
    p.update({k: v for k, v in params.items() if v is not None})
    d = await call(S, "GET", "/api", params=p)
    if isinstance(d, dict) and d.get("status") is False and d.get("error"):
        raise ServiceError(f"SABnzbd: {d['error']}")
    return d


def _slot(s: dict) -> dict:
    return {"nzo_id": s.get("nzo_id"), "name": s.get("filename"), "status": s.get("status"),
            "percentage": s.get("percentage"), "mb": s.get("mb"), "mbleft": s.get("mbleft"),
            "timeleft": s.get("timeleft"), "cat": s.get("cat"), "priority": s.get("priority"),
            "eta": s.get("eta")}


@ping(S)
async def _ping(cfg: dict) -> dict:
    # 'version' needs no key; 'queue' proves the key
    v = await call(S, "GET", "/api", params={"mode": "version", "output": "json"}, cfg_override=cfg)
    q = await call(S, "GET", "/api", params={"mode": "queue", "output": "json", "limit": 1}, cfg_override=cfg)
    if isinstance(q, dict) and q.get("error"):
        raise ServiceError(f"SABnzbd: {q['error']}")
    return {"version": (v or {}).get("version"), "detail": f"status {(q.get('queue') or {}).get('status')}"}


@tool(S)
async def sabnzbd_status() -> Any:
    """Overview: version, paused state, speed, free disk space, number of jobs and the first jobs in the queue."""
    q = (await sab("queue", limit=10)).get("queue", {})
    v = await sab("version")
    out = pick(q, ["status", "paused", "speed", "kbpersec", "speedlimit", "speedlimit_abs", "mb", "mbleft",
                   "timeleft", "eta", "diskspace1", "diskspace2", "diskspacetotal1", "noofslots_total"])
    out["version"] = v.get("version")
    out["jobs"] = [_slot(s) for s in q.get("slots", [])]
    return out


@tool(S)
async def sabnzbd_queue(limit: int = 50, start: int = 0, search: Optional[str] = None,
                        category: Optional[str] = None) -> Any:
    """Download queue (paged)."""
    q = (await sab("queue", limit=max(1, min(limit, 200)), start=start, search=search, cat=category)).get("queue", {})
    return {"total": q.get("noofslots_total"), "status": q.get("status"), "speed": q.get("speed"),
            "items": [_slot(s) for s in q.get("slots", [])]}


@tool(S)
async def sabnzbd_history(limit: int = 30, start: int = 0, search: Optional[str] = None,
                          category: Optional[str] = None, failed_only: bool = False) -> Any:
    """Completed / failed downloads."""
    h = (await sab("history", limit=max(1, min(limit, 200)), start=start, search=search, cat=category,
                   failed_only=1 if failed_only else None)).get("history", {})
    items = [{"nzo_id": s.get("nzo_id"), "name": s.get("name"), "status": s.get("status"), "size": s.get("size"),
              "category": s.get("category"), "completed": s.get("completed"),
              "fail_message": s.get("fail_message"), "storage": s.get("storage")} for s in h.get("slots", [])]
    return {"total": h.get("noofslots"), "items": items}


@tool(S, "write")
async def sabnzbd_add_url(url: str, name: Optional[str] = None, category: Optional[str] = None,
                          priority: Optional[str] = None) -> Any:
    """Add an NZB by URL. priority: force | high | normal | low."""
    prio = PRIO.get((priority or "").lower()) if priority else None
    if priority and prio is None:
        raise ServiceError(f"priority must be one of {', '.join(PRIO)}")
    return await sab("addurl", name=url, nzbname=name, cat=category, priority=prio)


@tool(S, "write")
async def sabnzbd_pause(minutes: Optional[int] = None) -> Any:
    """Pause the whole queue, optionally for a number of minutes."""
    if minutes:
        return await sab("config", name="set_pause", value=minutes)
    return await sab("pause")


@tool(S, "write")
async def sabnzbd_resume() -> Any:
    """Resume the queue."""
    return await sab("resume")


@tool(S, "write")
async def sabnzbd_set_speed_limit(limit: str) -> Any:
    """Set the speed limit: a percentage of the line speed ('50'), an absolute value ('5M', '800K') or '0' for unlimited."""
    return await sab("config", name="speedlimit", value=limit)


@tool(S, "write")
async def sabnzbd_pause_item(nzo_id: str) -> Any:
    """Pause one job."""
    return await sab("queue", name="pause", value=nzo_id)


@tool(S, "write")
async def sabnzbd_resume_item(nzo_id: str) -> Any:
    """Resume one job."""
    return await sab("queue", name="resume", value=nzo_id)


@tool(S, "write")
async def sabnzbd_set_priority(nzo_id: str, priority: str) -> Any:
    """Set job priority: force | high | normal | low."""
    if priority.lower() not in PRIO:
        raise ServiceError(f"priority must be one of {', '.join(PRIO)}")
    return await sab("queue", name="priority", value=nzo_id, value2=PRIO[priority.lower()])


@tool(S, "destructive")
async def sabnzbd_delete_queue_item(nzo_id: str, delete_files: bool = False) -> Any:
    """Remove a job from the queue (delete_files also removes partial files)."""
    return await sab("queue", name="delete", value=nzo_id, del_files=1 if delete_files else None)


@tool(S, "write")
async def sabnzbd_retry(nzo_id: Optional[str] = None) -> Any:
    """Retry a failed download from history; without nzo_id all failed jobs are retried."""
    if nzo_id:
        return await sab("retry", value=nzo_id)
    return await sab("retry_all")


@tool(S, "destructive")
async def sabnzbd_delete_history(nzo_id: str, delete_files: bool = False) -> Any:
    """Delete history entries: an nzo_id, 'failed' (all failed) or 'all' (everything)."""
    return await sab("history", name="delete", value=nzo_id, del_files=1 if delete_files else None)


@tool(S)
async def sabnzbd_server_stats() -> Any:
    """Downloaded volume per news server and period."""
    return await sab("server_stats")


@tool(S)
async def sabnzbd_warnings() -> Any:
    """Recent warnings and errors."""
    d = await sab("warnings")
    return d.get("warnings", d)


@tool(S)
async def sabnzbd_categories() -> Any:
    """Configured categories."""
    d = await sab("get_cats")
    return d.get("categories", d)


@tool(S)
async def sabnzbd_get_config(section: Optional[str] = None) -> Any:
    """Read the SABnzbd configuration (optionally one section, e.g. 'misc', 'servers', 'categories'). Secrets are masked."""
    d = await sab("get_config", section=section)
    return redact(d.get("config", d))


@tool(S, "destructive")
async def sabnzbd_restart() -> Any:
    """Restart SABnzbd."""
    return await sab("restart")


@tool(S, "write", mixed=True)
async def sabnzbd_api_request(mode: str, params: Optional[dict] = None) -> Any:
    """Raw SABnzbd API call: mode plus extra parameters, e.g. mode='queue', params={'name':'rename','value':'<nzo>','value2':'new name'}. Read-only modes only in read-only mode."""
    params = dict(params or {})
    params.pop("apikey", None)
    is_write = mode not in READ_MODES or (mode in ("queue", "history") and "name" in params)
    if is_write and CONFIG.service(S)["read_only"]:
        raise ServiceError("Service 'sabnzbd' is in read-only mode.")
    return redact(await sab(mode, **params))
