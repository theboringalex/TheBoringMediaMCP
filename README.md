<p align="center">
  <img src="assets/logo.png" alt="TheBoringMediaMCP" width="220">
</p>

<h1 align="center">TheBoringMediaMCP</h1>

<p align="center">
  One <a href="https://modelcontextprotocol.io">MCP</a> server for your whole media stack –<br>
  <b>Jellyfin · Radarr · Sonarr · Prowlarr · Seerr · SABnzbd · Gluetun · Homarr · Jellyfin Collection</b><br>
  with a web UI, as a <b>Home Assistant add-on</b> or Docker container, for <b>every AI client</b> (Claude, ChatGPT, Gemini, Cursor, n8n, …).
</p>

<p align="center">
  <a href="docs/ANLEITUNG.md">🇩🇪 Anleitung</a> ·
  <a href="docs/GUIDE.md">🇬🇧 Guide</a> ·
  <a href="CHANGELOG.md">Changelog</a>
</p>

---

> *"Request the new Dune movie, show me what SABnzbd is downloading, and restart the VPN if the IP is in the wrong country."* – one sentence, three services.

## Features

- **136 tools** across 9 services – search & add movies/series, queue and history, interactive release search, Jellyfin libraries/sessions/collections/tasks, Seerr requests, SABnzbd control, Gluetun VPN restart, indexer tests, `jfc` collection runs …
- **Web UI** (German/English, light/dark): enable services, enter URL + API key, **test the connection**, copy ready-made connection snippets, browse all tools, watch the call log.
- **Works with every MCP client**: Streamable HTTP (`/mcp`), legacy SSE (`/sse`) and stdio (`--stdio`). Auth by `Authorization: Bearer`, `X-API-Key`, `?token=` **or a secret URL** (`/s/<token>/mcp`) for clients that only accept a URL (claude.ai, ChatGPT).
- **Beats the 100-tool limit**: besides `/mcp` (everything) there are split endpoints – `/mcp/arr`, `/mcp/downloads`, `/mcp/media` and one per service (`/mcp/radarr`, …). Add several connectors instead of one huge one.
- **Safe by design**: per-service **read-only mode** (write tools disappear), tool annotations (read / write / destructive) so clients ask before deleting, secrets are masked in everything the AI can read, no outbound calls except to your own services.
- **Home Assistant add-on** with Ingress (sidebar entry) – or plain **Docker Compose** without any `.env` file.

## Quick start

### Home Assistant add-on
1. *Settings → Add-ons → Add-on store → ⋮ → Repositories* → add `https://github.com/theboringalex/TheBoringMediaMCP`
2. Install **TheBoringMediaMCP**, start it, open the web UI (sidebar *Media MCP*).
3. Enable your services, enter URL + API key, press **Test**, **Save**.
4. Open the **Connect** tab and copy the snippet for your AI.

### Docker Compose
```bash
git clone https://github.com/theboringalex/TheBoringMediaMCP.git
cd TheBoringMediaMCP
nano docker-compose.yml        # set TBMM_TOKEN and your service URLs / keys
docker compose up -d --build
```
Web UI: `http://<server>:17830` · MCP endpoint: `http://<server>:17830/mcp`

### Local (stdio, e.g. Claude Desktop without a server)
```bash
pip install -r theboringmediamcp/app/requirements.txt
cd theboringmediamcp/app
TBMM_RADARR_URL=http://nas:7878 TBMM_RADARR_API_KEY=… python -m theboringmediamcp --stdio
```

## Endpoints

| Path | Tools | Content |
|---|---|---|
| `/mcp` | all enabled | everything (136 with all services on) |
| `/mcp/arr` | 71 | Radarr, Sonarr, Prowlarr, Seerr |
| `/mcp/downloads` | 28 | SABnzbd, Gluetun |
| `/mcp/media` | 33 | Jellyfin, Jellyfin Collection |
| `/mcp/<service>` | 4–22 | `jellyfin`, `radarr`, `sonarr`, `prowlarr`, `seerr`, `sabnzbd`, `gluetun`, `homarr`, `jellyfin_collection` |
| `/sse` | all | legacy HTTP+SSE transport |
| `/` | – | web UI |
| `/healthz` | – | health check (no auth) |

Only tools of **enabled** services are listed.

## Services

| Service | Needs | Highlights |
|---|---|---|
| Jellyfin | URL + API key | search, browse, latest, sessions, scheduled tasks, library scan, **collections** (create/add/remove), delete |
| Radarr / Sonarr | URL + API key | lookup, add (sensible defaults), update, delete, queue, calendar, history, missing, search, interactive releases + grab, commands |
| Prowlarr | URL + API key | indexers (enable/test), search across indexers, grab, stats, app sync |
| Seerr (Seerr/Jellyseerr/Overseerr) | URL + API key | search, discover, create/approve/decline requests, issues |
| SABnzbd | URL + API key | queue, history, add NZB URL, pause/resume, speed limit, priorities, retry, stats |
| Gluetun | control-server URL (+ key) | status, public IP, **restart VPN**, forwarded port, DNS |
| Homarr | URL + API key | status, OpenAPI path discovery, boards, raw API |
| Jellyfin Collection (`jfc`) | Docker endpoint + container name | run/validate/list/test, logs, read & write collection YAML (via Docker API, since `jfc` has no HTTP API) |

Every service also has a raw `*_api_request` tool, so nothing is out of reach.

## Configuration

Values saved in the web UI win. Environment variables (`TBMM_<SERVICE>_URL`, `TBMM_<SERVICE>_API_KEY`, `TBMM_TOKEN`, `TBMM_PUBLIC_URL`, …) and Home Assistant add-on options only provide **start values**. Data lives in `/data/config.json` (mode 600).

## Security notes

- Always set a long random token; expose the server only through HTTPS (e.g. Nginx Proxy Manager) or a VPN such as Tailscale.
- The *secret URL* contains the token – treat it like a password.
- Docker socket access (for `jfc`) is root-equivalent: prefer a [socket proxy](docs/GUIDE.md#jellyfin-collection) with only `CONTAINERS` and `EXEC` allowed.
- Use **read-only** for services you only want to look at.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r theboringmediamcp/app/requirements.txt
cd theboringmediamcp/app && python -m theboringmediamcp --port 17830
```
Tools live in `theboringmediamcp/app/theboringmediamcp/tools/<service>.py`; a new tool is one decorated async function.

## License

[MIT](LICENSE) © theboringAlex
