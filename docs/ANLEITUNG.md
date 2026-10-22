# TheBoringMediaMCP – Anleitung (Deutsch)

<p align="center"><img src="../assets/logo.png" width="140" alt="TheBoringMediaMCP"></p>

Diese Anleitung führt dich Schritt für Schritt von „nichts installiert“ bis „meine KI steuert Jellyfin, Radarr, Sonarr & Co.“. Du brauchst keine Programmierkenntnisse.

**Inhalt**
1. [Was ist das?](#1-was-ist-das)
2. [Was du vorher brauchst (API-Keys)](#2-was-du-vorher-brauchst)
3. [Installation als Home-Assistant-Add-on](#3-installation-als-home-assistant-add-on)
4. [Installation mit Docker Compose](#4-installation-mit-docker-compose)
5. [Dienste in der Weboberfläche einrichten](#5-dienste-in-der-weboberfläche-einrichten)
6. [Von außen erreichbar machen](#6-von-außen-erreichbar-machen)
7. [KI verbinden](#7-ki-verbinden) – Claude, ChatGPT, Gemini, Cursor/VS Code, n8n
8. [Das 100-Tools-Limit und die Teil-Endpunkte](#8-das-100-tools-limit-und-die-teil-endpunkte)
9. [Beispiele zum Ausprobieren](#9-beispiele-zum-ausprobieren)
10. [Sonderfälle: Gluetun, Homarr, Jellyfin Collection](#10-sonderfälle)
11. [Sicherheit](#11-sicherheit)
12. [Fehlersuche](#12-fehlersuche)
13. [Aktualisieren](#13-aktualisieren)

---

## 1. Was ist das?

Ein **MCP-Server** ist eine Art Steckdose, über die eine KI (Claude, ChatGPT, Gemini …) Werkzeuge benutzen darf. **TheBoringMediaMCP** bringt die Werkzeuge für deinen Medien-Stack mit:

| Dienst | Wofür |
|---|---|
| Jellyfin | Mediathek, Suche, Sitzungen, Sammlungen, Aufgaben |
| Radarr / Sonarr | Filme / Serien suchen, hinzufügen, Warteschlange, Verlauf |
| Prowlarr | Indexer verwalten und testen, übergreifend suchen |
| Seerr (Jellyseerr/Overseerr) | Wünsche (Requests) anlegen und freigeben |
| SABnzbd | Downloads steuern |
| Gluetun | VPN-Status, öffentliche IP, VPN neu starten |
| Homarr | Dashboard-Zugriff |
| Jellyfin Collection | Sammlungs-Manager `jfc` starten, Logs lesen, YAML bearbeiten |

Dazu gibt es eine **Weboberfläche**, in der du alles per Klick einstellst, und Fertig-Snippets zum Verbinden deiner KI.

## 2. Was du vorher brauchst

Für jeden Dienst, den du nutzen willst: **Adresse (URL)** und **API-Key**.

| Dienst | URL-Beispiel | API-Key finden |
|---|---|---|
| Jellyfin | `http://192.168.1.5:8096` | Dashboard → *API-Schlüssel* → **+** |
| Radarr | `http://192.168.1.5:7878` | Einstellungen → Allgemein → *API-Schlüssel* |
| Sonarr | `http://192.168.1.5:8989` | Einstellungen → Allgemein → *API-Schlüssel* |
| Prowlarr | `http://192.168.1.5:9696` | Einstellungen → Allgemein → *API-Schlüssel* |
| Seerr | `http://192.168.1.5:5055` | Einstellungen → Allgemein → *API-Schlüssel* |
| SABnzbd | `http://192.168.1.5:8080` | Config → Allgemein → *API-Schlüssel* |
| Gluetun | `http://192.168.1.5:8000` | meist kein Key nötig, siehe [Abschnitt 10](#gluetun) |
| Homarr | `http://192.168.1.5:7575` | Verwaltung → Tools → API → Schlüssel erstellen |
| Jellyfin Collection | – | braucht Docker-Zugriff, siehe [Abschnitt 10](#jellyfin-collection) |

> Tipp: Nimm die **IP-Adresse oder den Container-Namen**, unter dem TheBoringMediaMCP die Dienste erreicht. `localhost` zeigt im Container/Add-on auf den Container selbst, nicht auf deinen Server!

Nicht alle Dienste sind Pflicht – nur was du einschaltest, wird der KI angeboten.

## 3. Installation als Home-Assistant-Add-on

1. Home Assistant öffnen → **Einstellungen → Add-ons → Add-on-Store**.
2. Oben rechts **⋮ → Repositories** → diese Adresse einfügen und **Hinzufügen**:
   ```
   https://github.com/theboringalex/TheBoringMediaMCP
   ```
3. Seite neu laden, **TheBoringMediaMCP** auswählen → **Installieren**.
4. Optional in der Konfiguration ein eigenes **MCP-Zugangstoken** setzen (sonst wird eins erzeugt) und die öffentliche Basis-URL eintragen. **Starten**.
5. In der Seitenleiste erscheint **Media MCP** (oder *Web-UI öffnen*). Weiter mit [Abschnitt 5](#5-dienste-in-der-weboberfläche-einrichten).

Der MCP-Endpunkt ist danach unter `http://<home-assistant-ip>:17830/mcp` erreichbar.

## 4. Installation mit Docker Compose

```bash
git clone https://github.com/theboringalex/TheBoringMediaMCP.git
cd TheBoringMediaMCP
nano docker-compose.yml     # TBMM_TOKEN ändern, URLs/Keys eintragen
docker compose up -d --build
```

* Alle Werte stehen direkt in der `docker-compose.yml` – eine `.env`-Datei brauchst du nicht.
* In **Portainer**: *Stacks → Add stack → Repository* mit der GitHub-Adresse, oder den Inhalt der Compose-Datei in den Web-Editor kopieren.
* Weboberfläche: `http://<server-ip>:17830`. Anmelden mit deinem `TBMM_TOKEN`.
* Die Angaben in der Compose-Datei sind **Startwerte**. Was du später in der Weboberfläche speicherst, hat Vorrang und liegt im Volume `/data`.

## 5. Dienste in der Weboberfläche einrichten

1. Reiter **Dienste** öffnen.
2. Pro Dienst: **URL** und **API-Key** eintragen, Schalter **Aktiv** einschalten.
3. **Testen** drücken – grüner Punkt und Version = alles in Ordnung. Bei Fehlern steht der Grund direkt dabei (falsche IP, falscher Key …).
4. **Speichern** (unten).
5. Optional pro Dienst:
   * **Nur lesen** – die KI kann nichts ändern; alle schreibenden Tools verschwinden.
   * **TLS-Zertifikat prüfen** – bei selbstsignierten Zertifikaten ausschalten.
6. Im Reiter **Übersicht** siehst du alle Dienste mit Status und Tool-Anzahl, unter **Tools** die komplette Werkzeugliste, unter **Protokoll** die letzten KI-Aufrufe.

## 6. Von außen erreichbar machen

Claude.ai und ChatGPT laufen in der Cloud und müssen deinen Server per **HTTPS** erreichen. Mit Nginx Proxy Manager (NPM):

1. **Proxy Host** anlegen: Domain z. B. `mediamcp.deinedomain.de` → Ziel `http://<ip>:17830`.
2. SSL: Let's-Encrypt-Zertifikat, **Force SSL** an.
3. Reiter **Advanced**, folgendes eintragen (wichtig für Streaming-Verbindungen):
   ```nginx
   proxy_buffering off;
   proxy_read_timeout 86400s;
   proxy_send_timeout 86400s;
   chunked_transfer_encoding off;
   ```
4. In der Weboberfläche unter **Dienste → Allgemein** die **Öffentliche Basis-URL** `https://mediamcp.deinedomain.de` eintragen – danach stimmen alle Beispiele im Reiter **Verbinden**.

Wer nichts ins Internet stellen will, nutzt **Tailscale** (oder ein anderes VPN) und verbindet Clients über die Tailscale-Adresse.

> ⚠️ Mit dem Token kann jeder deine Dienste steuern. Nutze ein langes Zufallstoken und HTTPS.

## 7. KI verbinden

Öffne den Reiter **Verbinden**. Dort wählst du den Endpunkt (alles oder Teilbereich) und bekommst für jede KI ein fertiges Snippet mit **Kopieren**-Knopf. Zwei Verfahren:

* **URL mit Token** (`https://…/s/<token>/mcp`) – für Clients, die nur eine Adresse annehmen (claude.ai, ChatGPT). Funktioniert überall.
* **Bearer-Header** (`Authorization: Bearer <token>`) – etwas sauberer, für Clients mit Header-Feld.

### Claude (claude.ai, Claude Desktop, Handy-App)
*Einstellungen → Connectors → Benutzerdefinierten Connector hinzufügen* → Name `TheBoringMediaMCP`, URL aus dem Snippet (**URL mit Token**). Zugriffsrechte pro Tool lassen sich danach einstellen; „Genehmigung erforderlich“ ist für schreibende Tools sinnvoll.

**Claude Code (Terminal):**
```bash
claude mcp add --transport http theboringmediamcp https://mediamcp.deinedomain.de/mcp --header "Authorization: Bearer DEIN_TOKEN"
```
**Claude Desktop lokal über `mcp-remote`** (`claude_desktop_config.json`): Snippet im Reiter *Verbinden*.

### ChatGPT
*Einstellungen → Connectors → Erweitert → Entwicklermodus* aktivieren, dann *Erstellen* / *MCP-Server hinzufügen*: URL mit Token, Authentifizierung **keine**. (Verfügbarkeit hängt von deinem ChatGPT-Tarif ab.)

### Gemini
Gemini CLI: in `~/.gemini/settings.json` das Snippet unter `mcpServers` einfügen (`httpUrl` + `headers`).

### Cursor, Windsurf, VS Code, LM Studio, Open WebUI
Snippets im Reiter *Verbinden* – `url` + `headers.Authorization`.

### n8n
Im Workflow den Knoten **MCP Client Tool** verwenden: *Endpoint* = `https://…/mcp` (oder Teil-Endpunkt), *Server Transport* = **HTTP Streamable**, *Authentication* = **Bearer** mit deinem Token.

### Lokal ohne Server (stdio)
Siehe README – `python -m theboringmediamcp --stdio` mit `TBMM_…`-Umgebungsvariablen.

## 8. Das 100-Tools-Limit und die Teil-Endpunkte

Manche KI-Clients laden höchstens ~100 Tools pro Server; zu viele Tools verwirren zudem das Modell. Mit allen Diensten sind es 136. Deshalb gibt es **Teil-Endpunkte** – lege einfach mehrere Connectoren an:

| Pfad | Inhalt | Tools |
|---|---|---|
| `/mcp/arr` | Radarr, Sonarr, Prowlarr, Seerr | 71 |
| `/mcp/downloads` | SABnzbd, Gluetun | 28 |
| `/mcp/media` | Jellyfin, Jellyfin Collection | 33 |
| `/mcp/radarr`, `/mcp/sonarr`, … | ein einzelner Dienst | 4–22 |

Beispiel: Connector 1 = `…/mcp/arr`, Connector 2 = `…/mcp/downloads`, Connector 3 = `…/mcp/media`. In der Übersicht warnt dich die Oberfläche, wenn `/mcp` über 100 Tools liegt.

## 9. Beispiele zum Ausprobieren

* „Welche Downloads laufen gerade, und wie viel Platz ist frei?“
* „Suche *Dune Part Two* und lade den Film in 1080p herunter.“
* „Füge die Serie *Severance* hinzu, überwache alle Staffeln und suche fehlende Folgen.“
* „Welche Filme in Radarr haben noch keine Datei?“
* „Ist der Indexer *NZBgeek* in Prowlarr in Ordnung? Teste alle Indexer.“
* „Zeig offene Seerr-Anfragen und genehmige die von Marie.“
* „Wer schaut gerade was auf Jellyfin?“
* „Lege in Jellyfin eine Sammlung *Matrix-Filme* mit allen Matrix-Teilen an.“
* „Welche IP hat Gluetun? Starte das VPN neu und sag mir die neue IP.“
* „Starte `jfc` im Testlauf nur für die Bibliothek *Filme*.“

## 10. Sonderfälle

### Gluetun
Die Steuerung läuft über den **Gluetun Control Server** (Port 8000). Der Port muss vom MCP-Server erreichbar sein:
```yaml
gluetun:
  ports:
    - 8000:8000/tcp     # Control Server
```
* Standardmäßig braucht er **keinen** Key, solange Gluetun nicht im Internet steht. Hast du Authentifizierung aktiviert, trage den API-Key oder Benutzer/Passwort in der Weboberfläche ein.
* Läuft SABnzbd über `network_mode: service:gluetun`, erreichst du SABnzbd über den **Gluetun-Container** und dessen veröffentlichten SABnzbd-Port.
* „VPN neu starten“ unterbricht kurz alle Downloads – das ist der Kill-Switch und gewollt.

### Homarr
In Homarr: *Verwaltung → Tools → API* → Schlüssel erstellen (`id.token`) und in die Weboberfläche eintragen. Homarr ändert seine API zwischen Versionen; das Tool `homarr_api_paths` liest die Endpunkte der eigenen Instanz aus, `homarr_api_request` ruft sie auf.

### Jellyfin Collection
`jfc` hat keine HTTP-Schnittstelle. TheBoringMediaMCP steuert den Container deshalb über die **Docker-API** (`docker exec` und Logs). Zwei Wege:

**A) Docker-Socket durchreichen** (nur Docker Compose, nicht im HA-Add-on):
```yaml
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```
Docker-Endpunkt in der Oberfläche: `unix:///var/run/docker.sock`.

**B) Socket-Proxy (sicherer, auch fürs Add-on)** – gibt nur frei, was nötig ist:
```yaml
  docker-socket-proxy:
    image: tecnativa/docker-socket-proxy
    restart: unless-stopped
    environment:
      CONTAINERS: 1
      EXEC: 1
      POST: 1
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    ports:
      - "127.0.0.1:2375:2375"   # nur lokal bzw. nur im Heimnetz freigeben!
```
Docker-Endpunkt: `http://<server-ip>:2375`. **Container-Name**: der Name deines `jfc`-Containers (Standard `jellyfin-collection`).

> ⚠️ Docker-Zugriff ist Root-Zugriff auf den Server. Den Proxy niemals ins Internet stellen. Schreib-Funktionen (`jfc_write_config_file`, `jfc_exec`) kannst du mit **Nur lesen** abschalten.

## 11. Sicherheit

* **Starkes Token** (mindestens 32 Zeichen), Weboberfläche und MCP nur über HTTPS oder VPN erreichbar machen.
* Nach jedem Verdacht auf Weitergabe: Reiter *Verbinden* → **Neues Token erzeugen**.
* **Nur lesen** für alles, was die KI nur ansehen soll.
* Geheimnisse (API-Keys, Passwörter) werden in allem, was die KI lesen kann, **maskiert** (`***`). Trotzdem gilt: Die KI kann mit deinen Diensten alles tun, was ein Admin kann – lösch-/neustart-Tools sind als „destruktiv“ markiert, damit Clients nachfragen.
* Falsche Token-Versuche werden pro IP gebremst.

## 12. Fehlersuche

| Problem | Lösung |
|---|---|
| Dienst zeigt rot „cannot connect“ | URL/Port prüfen. Im Container nicht `localhost`, sondern die Server-IP oder den Container-Namen im selben Docker-Netz verwenden. |
| „authentication failed“ | API-Key falsch oder für falschen Dienst kopiert. |
| Verbinden in claude.ai/ChatGPT schlägt fehl | Muss per **HTTPS** und öffentlich erreichbar sein. NPM-Advanced-Einstellungen aus Abschnitt 6 prüfen. `https://…/healthz` im Browser öffnen – muss `ok` zeigen. |
| 401 Unauthorized | Token falsch oder Token wurde neu erzeugt. |
| Tools fehlen in der KI | Dienst aktiv? Nicht auf „Nur lesen“ (blendet schreibende Tools aus)? Connector in der KI trennen und neu verbinden, damit die Liste neu geladen wird. Mehr als 100 Tools → Teil-Endpunkte nutzen. |
| `jfc_*`: „Cannot reach the Docker endpoint“ | Socket nicht gemountet bzw. Proxy nicht erreichbar, Container-Name falsch. |
| Gluetun: HTTP 401/403 | Control Server hat Authentifizierung – Key oder Benutzer/Passwort eintragen. |

Logs: im Add-on der Reiter **Protokoll**, bei Docker `docker logs theboringmediamcp`. In der Weboberfläche zeigt **Protokoll** jeden Tool-Aufruf mit Dauer und Fehler.

## 13. Aktualisieren

* **Add-on:** Add-on-Store → *Nach Updates suchen* → **Aktualisieren**.
* **Docker:** `docker compose up -d --build` (holt die neueste Version von GitHub). Einstellungen bleiben im Volume `/data` erhalten.

---
Lizenz: MIT · Quellcode: <https://github.com/theboringalex/TheBoringMediaMCP>
