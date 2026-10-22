# TheBoringMediaMCP – Guide (English)

<p align="center"><img src="../assets/logo.png" width="140" alt="TheBoringMediaMCP"></p>

Step by step from "nothing installed" to "my AI controls Jellyfin, Radarr, Sonarr & friends". No programming needed. (Deutsche Fassung: [ANLEITUNG.md](ANLEITUNG.md))

**Contents** – [1 What it is](#1-what-it-is) · [2 Prerequisites](#2-prerequisites) · [3 Home Assistant add-on](#3-home-assistant-add-on) · [4 Docker Compose](#4-docker-compose) · [5 Web UI setup](#5-set-up-services-in-the-web-ui) · [6 Expose it](#6-make-it-reachable-from-outside) · [7 Connect your AI](#7-connect-your-ai) · [8 100-tool limit](#8-the-100-tool-limit-and-split-endpoints) · [9 Examples](#9-things-to-try) · [10 Special cases](#10-special-cases) · [11 Security](#11-security) · [12 Troubleshooting](#12-troubleshooting) · [13 Updating](#13-updating)

## 1. What it is

An **MCP server** lets an AI (Claude, ChatGPT, Gemini …) use tools. TheBoringMediaMCP provides the tools for your media stack: **Jellyfin, Radarr, Sonarr, Prowlarr, Seerr, SABnzbd, Gluetun, Homarr** and **Jellyfin Collection (`jfc`)** – 136 tools, a web UI to configure it, and ready-made connection snippets.

## 2. Prerequisites

For every service you want: its **URL** and **API key**.

| Service | Example URL | Where to find the key |
|---|---|---|
| Jellyfin | `http://192.168.1.5:8096` | Dashboard → API Keys → **+** |
| Radarr / Sonarr / Prowlarr | `…:7878` / `…:8989` / `…:9696` | Settings → General → API Key |
| Seerr | `http://192.168.1.5:5055` | Settings → General → API Key |
| SABnzbd | `http://192.168.1.5:8080` | Config → General → API Key |
| Gluetun | `http://192.168.1.5:8000` | usually none, see [§10](#gluetun) |
| Homarr | `http://192.168.1.5:7575` | Management → Tools → API → create key |
| Jellyfin Collection | – | Docker access, see [§10](#jellyfin-collection) |

> Use the **server IP or container name** the MCP server can reach. `localhost` inside a container/add-on is the container itself.

Only services you enable are offered to the AI.

## 3. Home Assistant add-on

1. *Settings → Add-ons → Add-on store → ⋮ → Repositories* → add `https://github.com/theboringalex/TheBoringMediaMCP`.
2. Reload, open **TheBoringMediaMCP** → **Install**.
3. Optionally set your own **MCP access token** and the public base URL in the configuration (a token is generated otherwise). **Start**.
4. Open **Media MCP** from the sidebar → continue with [§5](#5-set-up-services-in-the-web-ui).

MCP endpoint: `http://<home-assistant-ip>:17830/mcp`.

## 4. Docker Compose

```bash
git clone https://github.com/theboringalex/TheBoringMediaMCP.git
cd TheBoringMediaMCP
nano docker-compose.yml     # change TBMM_TOKEN, add URLs/keys
docker compose up -d --build
```
All values are written directly into the compose file – no `.env` needed. Web UI: `http://<server-ip>:17830` (sign in with `TBMM_TOKEN`). Compose values are **start values**; whatever you save in the UI wins and is stored in the `/data` volume.

## 5. Set up services in the web UI

1. Tab **Services** → enter **URL** and **API key**, switch **Enabled** on.
2. Press **Test** – green dot + version means it works; otherwise the reason is shown.
3. **Save**.
4. Optional per service: **Read-only** (all write tools disappear), **Verify TLS certificate** (turn off for self-signed certs).
5. **Overview** shows status and tool counts, **Tools** lists everything, **Log** shows the latest AI calls.

## 6. Make it reachable from outside

claude.ai and ChatGPT run in the cloud and need **HTTPS**. With Nginx Proxy Manager: create a proxy host → `http://<ip>:17830`, Let's Encrypt, Force SSL, and under *Advanced*:

```nginx
proxy_buffering off;
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
chunked_transfer_encoding off;
```
Then enter the **public base URL** under *Services → General* so the snippets in **Connect** are correct. Prefer not to open anything? Use **Tailscale**/a VPN.

## 7. Connect your AI

Open **Connect**, pick an endpoint, copy the snippet. Two auth styles:

* **URL with token** (`https://…/s/<token>/mcp`) – for clients accepting only a URL (claude.ai, ChatGPT).
* **Bearer header** (`Authorization: Bearer <token>`) – for clients with a header field.

| Client | How |
|---|---|
| **Claude** (claude.ai / Desktop / mobile) | Settings → Connectors → *Add custom connector* → URL with token |
| **Claude Code** | `claude mcp add --transport http theboringmediamcp https://…/mcp --header "Authorization: Bearer TOKEN"` |
| **ChatGPT** | Settings → Connectors → Advanced → Developer mode → add MCP server, URL with token, authentication none |
| **Gemini CLI** | `~/.gemini/settings.json` → `mcpServers` → `httpUrl` + `headers` |
| **Cursor / Windsurf / VS Code / LM Studio / Open WebUI** | `url` + `headers.Authorization` (snippets in the UI) |
| **n8n** | *MCP Client Tool* node → endpoint, transport *HTTP Streamable*, bearer auth |
| **Local stdio** | `python -m theboringmediamcp --stdio` with `TBMM_*` environment variables |

## 8. The 100-tool limit and split endpoints

Some clients load at most ~100 tools per server, and too many tools confuse models. All services together: 136. Add several connectors instead:

| Path | Content | Tools |
|---|---|---|
| `/mcp/arr` | Radarr, Sonarr, Prowlarr, Seerr | 71 |
| `/mcp/downloads` | SABnzbd, Gluetun | 28 |
| `/mcp/media` | Jellyfin, Jellyfin Collection | 33 |
| `/mcp/<service>` | one service | 4–22 |

## 9. Things to try

* "What is downloading right now and how much disk space is left?"
* "Find *Dune Part Two* and download it in 1080p."
* "Add *Severance*, monitor all seasons and search for missing episodes."
* "Which Radarr movies have no file yet?" · "Test all Prowlarr indexers."
* "Show pending Seerr requests and approve the one from Marie."
* "Who is watching what on Jellyfin?" · "Create a Jellyfin collection *Matrix films*."
* "What's Gluetun's public IP? Restart the VPN and tell me the new one."
* "Run `jfc` as a dry run for the library *Films* only."

## 10. Special cases

### Gluetun
Uses the **control server** (port 8000) – publish it: `ports: ["8000:8000/tcp"]`. No key needed unless you enabled control-server auth; then enter API key or user/password. If SABnzbd runs through `network_mode: service:gluetun`, reach it via the Gluetun container's published port. Restarting the VPN briefly interrupts downloads (kill switch, intended).

### Homarr
Create an API key (*Management → Tools → API*, format `id.token`). The API differs between Homarr versions: `homarr_api_paths` reads your instance's OpenAPI spec, `homarr_api_request` calls any endpoint.

### Jellyfin Collection
`jfc` has no HTTP API, so the server uses the **Docker API** (`docker exec`, logs).

**A) Mount the socket** (Compose only, not the HA add-on): `- /var/run/docker.sock:/var/run/docker.sock`, endpoint `unix:///var/run/docker.sock`.

**B) Socket proxy (safer, works for the add-on too):**
```yaml
  docker-socket-proxy:
    image: tecnativa/docker-socket-proxy
    restart: unless-stopped
    environment: { CONTAINERS: 1, EXEC: 1, POST: 1 }
    volumes: ["/var/run/docker.sock:/var/run/docker.sock:ro"]
    ports: ["127.0.0.1:2375:2375"]   # LAN/localhost only!
```
Endpoint `http://<server-ip>:2375`, container name = your `jfc` container (default `jellyfin-collection`).

> ⚠️ Docker access is root-equivalent. Never expose the proxy to the internet. Use **Read-only** to disable the write tools.

## 11. Security

* Long random token, HTTPS or VPN only; regenerate under **Connect → Generate new token** if in doubt.
* Use **Read-only** for services the AI should only look at.
* Secrets are **masked** (`***`) in everything the AI can read. The AI can still do anything an admin can do – delete/restart tools are annotated *destructive* so clients ask first.
* Failed token attempts are rate-limited per IP.

## 12. Troubleshooting

| Problem | Fix |
|---|---|
| Red "cannot connect" | Check URL/port; inside containers use the server IP or a container name on the same Docker network, not `localhost`. |
| "authentication failed" | Wrong API key or key of another service. |
| claude.ai / ChatGPT cannot connect | Must be public **HTTPS**. Check the NPM *Advanced* block; open `https://…/healthz` – it must say `ok`. |
| 401 Unauthorized | Wrong or regenerated token. |
| Tools missing | Service enabled? Not read-only? Disconnect and reconnect the connector to reload the tool list. Over 100 tools → use split endpoints. |
| `jfc_*` "Cannot reach the Docker endpoint" | Socket not mounted / proxy unreachable / wrong container name. |
| Gluetun 401/403 | Control-server auth is on – enter key or user/password. |

Logs: `docker logs theboringmediamcp` or the add-on *Log* tab; the UI's **Log** tab lists every tool call.

## 13. Updating

* **Add-on:** Add-on store → check for updates → **Update**.
* **Docker:** `docker compose up -d --build`. Settings stay in `/data`.

---
License: MIT · Source: <https://github.com/theboringalex/TheBoringMediaMCP>
