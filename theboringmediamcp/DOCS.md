# TheBoringMediaMCP

MCP server for **Jellyfin, Radarr, Sonarr, Prowlarr, Seerr, SABnzbd, Gluetun, Homarr and Jellyfin Collection** – usable from Claude, ChatGPT, Gemini, Cursor, n8n and every other MCP client.

## Setup in 3 steps

1. Start the add-on and open **Media MCP** in the sidebar (or *Open web UI*).
2. Tab **Services**: enter URL + API key per service, enable it, press **Test**, **Save**.
3. Tab **Connect**: copy the snippet for your AI.

## Add-on options

| Option | Meaning |
|---|---|
| `mcp_token` | Secret AI clients must send. Empty = generated automatically and shown in the web UI (tab *Connect*). |
| `public_url` | Public HTTPS address of this add-on, e.g. `https://media-mcp.example.com` (without `/mcp`). Only used for the examples in the UI. |
| `language` | Web UI language (`de` / `en`). |
| `log_level` | `debug`, `info`, `warning`, `error`. |

Everything else (services, URLs, keys, read-only mode) is configured in the web UI and stored in the add-on's data folder.

## Endpoints (port 17830)

* `/mcp` – all enabled services · `/mcp/arr` · `/mcp/downloads` · `/mcp/media` · `/mcp/<service>`
* `/sse` – legacy SSE transport · `/healthz` – health check

Clients that only accept a URL (claude.ai, ChatGPT) use `https://<host>/s/<token>/mcp`; clients with a header field use `Authorization: Bearer <token>`.

Expose the port only via HTTPS (e.g. Nginx Proxy Manager) or a VPN. Full guide: https://github.com/theboringalex/TheBoringMediaMCP/blob/main/docs/GUIDE.md
