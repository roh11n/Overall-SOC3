# MSSP-Overview — Deployment Runbook (self-hosted, local LLM via Ollama)

This packages the whole app — **FastAPI backend + React frontend + MongoDB + a
local Ollama LLM (IRIS)** — into one `docker compose` stack you run on your own
Linux VM or box. IRIS answers chat questions using a **real local model**
(default `qwen2.5:1.5b`) served by Ollama — nothing is sent to a third‑party API.

---

## 1. Requirements
- A Linux host with **Docker** + **Docker Compose v2** (`docker compose version`).
- **RAM:** 4 GB minimum (`qwen2.5:1.5b`). Use `qwen2.5:0.5b`/`llama3.2:1b` for ~2–3 GB; `qwen2.5:3b` wants 6 GB+.
- ~6 GB free disk (images + model weights + Mongo data).
- Open inbound port 80 (or whatever you set as `HTTP_PORT`).

## 2. Configure
```bash
cp .env.example .env
# generate a strong secret and paste it into JWT_SECRET
openssl rand -hex 32
nano .env          # set JWT_SECRET, ADMIN_PASSWORD, (optional) OLLAMA_MODEL, HTTP_PORT
```

## 3. Launch
```bash
docker compose up -d --build
```
On first boot the backend automatically tells Ollama to pull the model. Watch progress:
```bash
docker compose logs -f backend    # look for "Ollama model ... ready: True"
```
The IRIS copilot works immediately in **rule-based fallback** and switches to the
**local LLM** as soon as the pull finishes (a few minutes on first run only).

## 4. Verify (smoke test)
```bash
curl http://localhost/api/            # -> {"service":"mssp-soc-dashboard","status":"ok"}
```
Then open `http://<server-ip>/` and sign in. Seeded logins (change the admin password!):

| Role | Email | Password |
|---|---|---|
| admin | admin@mssp-soc.io | (your ADMIN_PASSWORD) |
| soc_manager | soc.manager@mssp-soc.io | SocManager@2026! |
| client | client@mssp-soc.io | Client@2026! |
| detection_engineer | detection@mssp-soc.io | Detection@2026! |
| ti_analyst | ti.analyst@mssp-soc.io | TiAnalyst@2026! |
| automation_engineer | automation@mssp-soc.io | Automation@2026! |

Confirm IRIS is on the local model: **Settings / copilot status** shows
`provider: ollama`, `ready: true` (or `GET /api/copilot/status`).

---

## 5. Migrate existing data (optional)
From your current machine, dump then restore into the compose Mongo:
```bash
# on the old box
mongodump --uri="mongodb://localhost:27017" --db=<old_db> --out=./dump

# copy ./dump to the new server, then:
docker cp ./dump $(docker compose ps -q mongo):/dump
docker compose exec mongo mongorestore --drop --db=mssp_soc /dump/<old_db>
```
Set `DB_NAME=mssp_soc` in `.env` to match (or restore into whatever `DB_NAME` you chose).

## 6. Hardening for public exposure
- **TLS (HTTPS):** put Caddy or Nginx in front for automatic Let's Encrypt. Minimal Caddy example:
  ```
  your-domain.com {
      reverse_proxy localhost:80
  }
  ```
  (Set `HTTP_PORT=8080` in `.env` so Caddy owns 80/443.)
- **Change `ADMIN_PASSWORD`** and rotate `JWT_SECRET` before go‑live.
- **MongoDB:** already **not** exposed to the internet (no published 27017). To add auth,
  set `MONGO_INITDB_ROOT_USERNAME`/`MONGO_INITDB_ROOT_PASSWORD` on the `mongo` service and
  update `MONGO_URL` to `mongodb://user:pass@mongo:27017/?authSource=admin`.
- **Firewall:** only allow 80/443 inbound.

## 7. Operations
```bash
docker compose ps                 # status
docker compose logs -f backend    # backend logs
docker compose restart backend    # restart a service
docker compose down               # stop (keeps data volumes)
docker compose down -v            # stop + WIPE data (mongo + ollama volumes)
```
Data persists in the `mongo_data` and `ollama_data` named volumes across restarts.

---

## Configuration reference (`.env`)
| Key | Purpose | Default |
|---|---|---|
| `DB_NAME` | Mongo database name | `mssp_soc` |
| `JWT_SECRET` | **Required.** Signs auth tokens | — |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Seeded admin login | admin@mssp-soc.io / — |
| `OLLAMA_MODEL` | Local LLM tag IRIS uses | `qwen2.5:1.5b` |
| `HTTP_PORT` | Host port for the web app | `80` |
| `CORS_ORIGINS` | Allowed origins (same‑origin => `*` is fine) | `*` |

Backend also reads `MONGO_URL` and `OLLAMA_BASE_URL`, which compose sets to the
internal service names (`mongodb://mongo:27017`, `http://ollama:11434`).
