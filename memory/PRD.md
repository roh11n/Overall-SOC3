# PRD — Overall-SOC-2 (MSSP SOC Analytics Dashboard) — Emergent Deployment

## Original problem statement
Deploy the Overall-SOC-2 repo so the IRIS assistant runs a **real local LLM (Ollama + qwen2.5:1.5b)** instead of the rule-based fallback. User decision: run everything **inside the Emergent environment** and actually install Ollama + pull `qwen2.5:1.5b` locally in the pod. Deployment/config task on an already-built repo — no source code changes.

## Architecture (as deployed here)
- **Frontend:** React (CRACO), supervisor `frontend` :3000, calls backend via `REACT_APP_BACKEND_URL`.
- **Backend:** FastAPI, supervisor `backend` :8001, all routes under `/api`.
- **DB:** MongoDB (supervisor `mongodb`), `DB_NAME=mssp_soc`.
- **LLM:** Ollama as a **new supervisor program `ollama`** (`/root/ollama/bin/ollama serve` on 127.0.0.1:11434), model `qwen2.5:1.5b`. Backend `llm.py` reads `OLLAMA_BASE_URL` / `OLLAMA_MODEL` from `backend/.env`.
- Ollama binary + libs in **/root/ollama**, models in **/root/.ollama** (persistent). Supervisor conf: `/etc/supervisor/conf.d/ollama.conf`.

## Config applied (Phase 2)
- Fresh `JWT_SECRET` (openssl 32-byte hex). New `ADMIN_PASSWORD` (not from git history) — see `/app/memory/test_credentials.md`.
- `MONGO_URL`, `DB_NAME`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` set in `backend/.env`.

## Verified (2026-06)
- Ollama installed to persistent `/root/ollama`; `qwen2.5:1.5b` pulled + loaded.
- Startup seeds admin + demo tenants (`all`, `acme-corp`, `globalbank`).
- Phase-4 smoke tests PASS: `/api/health` OK; admin login 200; XSOAR CSV → Executive KPIs live; PPTX 200; **IRIS chat real model (`source: hf-llm`, `model: qwen2.5:1.5b`)**.
- Testing agent: 100% backend + 100% frontend; all persona routes render clean.
- Demo data: `/app/sample_xsoar.csv` ingested for tenant `all`.

## Known caveat — pod inactivity restart
`/app` and `/root` persist; `/etc` and `/usr/local` may be wiped on long inactivity restart. Ollama binary/model persist in `/root`; supervisor conf may need re-arming. If IRIS falls back to `source: rule`:
```
sudo supervisorctl reread && sudo supervisorctl update && sudo supervisorctl start ollama
```

## Backlog
- P1: Self-heal — backend startup launches `ollama serve` from `/root/ollama/bin` if endpoint unreachable, surviving pod restarts with zero manual steps.
- P2: Upload real XSOAR/rules/threat-intel/log-validation exports to populate all dashboards.
- P2: TLS/domain fronting — only for the VM/self-host path (repo `DEPLOYMENT.md`), not needed inside Emergent.

## Iteration 2 (2026-06) — SOC analytics enhancements
- Fixed MITRE ATT&CK Coverage Heatmap showing zero (overlay now handles column-name variants + multi-valued tactics/techniques; coverage ~92.9% on seeded data).
- New QRadar offense ingest (`qradar_ingest.py`): counts offenses + false positives from `localizedCloseReason`. Endpoint `/api/dashboard/qradar`; SOC Manager KPIs.
- New Log Sources ingest (`logsources_ingest.py`): Total Enabled Log Sources + Log Sources Added KPIs. Endpoint `/api/dashboard/log-sources`; upload source `log_sources`.
- Resolution Mix: closedreason 'Other' + closednotes containing false positive / non-issue / merged offense now counted as False Positive.
- Detection Engineering: 'Finetuning Required' KPI + alert names from closedreason 'Other' + notes containing finetuning/tuned.
- PPTX: QRadar offenses wired into exec-overview (template idx 44) + native fallback exec-overview shows offenses & false positives.
- CAVEAT: exact placeholder for the client's reference "False Positive 8,086" incident-management tile could not be mapped 1:1 without the reference PPTX; needs the reference deck to pin the exact shape.
- Test fixtures: /app/sample_xsoar_v2.csv, /app/sample_qradar.csv, /app/sample_logsources.csv (ingested for tenant 'all').
