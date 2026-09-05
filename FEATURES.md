# MSSP SOC Console — Features & KPI Reference

Everything is **live-only**: dashboards are empty until you upload data, then every
number is computed from your files. Nothing is mocked/fabricated.

---

## 1. Data Sources (Uploads)

Upload via the **Upload** button (SOC Manager, Threat Intel, Detection pages). Pick a
Source; the file is bound to the **currently selected tenant** and replaces that
tenant's previous data for that source. CSV and Excel (.xlsx, all sheets scanned).

| Source | Key columns | Feeds |
|---|---|---|
| **XSOAR** (incidents) | Name, Severity, Status, Close Reason, Occurred, Closed, Rule Name, MITRE Tactic/Technique Name, Auto Close, SLA Breached | SOC Manager, SOAR, Executive, Client, Detection rule triggers |
| **Threat Intel** | Name/Advisory Name, Industry, Date of Release, IPs, Domain, Hash, Hash Type | Threat Intel dashboard, Executive advisories |
| **Rule Catalog** | Rule Name, Rule ID, Rule UUID, Description, Applicable Log Sources, ATT&CK Tactic, ATT&CK Technique (`;`-separated ok) | Detection MITRE coverage, coverage KPIs, Rule Effectiveness |
| **Log Validation** | Priority | Detection "Log Source Priority" pie |
| **QRadar** | (stored only) | Not wired to dashboards yet |

Upload feedback is honest: it reports **bound rows**, warns on wrong source (QRadar)
or **0-row column mismatch**, and dashboards auto-refresh (no reload).

---

## 2. Executive Overview  (`/`)
Composite view from XSOAR (+ Threat Intel + rule catalog). Empty until data exists.

| KPI | How it's computed |
|---|---|
| Incidents | Count of XSOAR incidents |
| SLA Compliance % | 100 − (SLA-breached ÷ total) |
| MTTR (h) | Avg (closed − occurred) across incidents |
| Automation Rate % | Auto-closed ÷ total |
| Detection Coverage % | Distinct MITRE tactics seen ÷ 14 (or rule-catalog coverage if uploaded) |
| False Positive Rate % | Close Reason = "False Positive" ÷ closed |
| Advisories | Total from Threat Intel upload |
| Health Score | 0.5·SLA + 0.3·Automation + 0.2·Detection coverage |
| Risk Score | 0.5·FP + 0.3·(100−SLA) + 0.2·min(100, MTTR) |
| Incident / SLA trends | Daily buckets from Occurred dates |
| AI Recommendations | Rule engine over the above thresholds, optionally rewritten by IRIS |

---

## 3. SOC Manager  (`/soc-manager`)
Operational view from XSOAR.

| KPI | How it's computed |
|---|---|
| Total / Open / Closed | Counts by Status |
| MTTR, SLA %, FP % | As above |
| **Severity Mix** | Incidents grouped by normalized Severity — **only High / Medium / Low** shown (grey/zero and non-standard/numeric values dropped) |
| Top Rules (noisy) | Rules ranked by FP rate (min 3 incidents) |
| Trends | Daily incident / SLA / automation buckets |

---

## 4. Client  (`/client`)
Business-risk view for one tenant from XSOAR (+ TI).

| KPI | How it's computed |
|---|---|
| Composite Risk | 0.4·FP rate + 0.6·breach rate |
| Quarterly SLA % | 100 − breach rate |
| Major (P1/P2) | Incidents with Severity Critical/High |
| **Repeat Incidents** | **Duplicate occurrences** — extra copies of the same incident/rule name (Σ count−1 over names seen >1) |
| Open Critical | Non-closed Critical incidents |
| Avg Dwell (h) | Avg MTTR |
| Top Targeted Assets | Most frequent Destination IPs |
| Top Attacking Sources | Most frequent Source IPs |
| Phishing Incidents | Category contains "phish" |
| **YoY* Incidents / MTTR / SLA** | Latest vs previous month present in the data (*month-over-month; true YoY needs a full year of history) |
| Threat Exposure | Advisory totals/timeline from Threat Intel |

---

## 5. Detection Engineering  (`/detection`)
Driven by the **Rule Catalog** (+ XSOAR triggers + Log Validation).

**Coverage KPIs** (from the rule catalog):
| KPI | How it's computed | Available? |
|---|---|---|
| MITRE Coverage % | Distinct ATT&CK tactics ÷ 14 | ✅ |
| Detection Coverage % | Rules mapped to ATT&CK ÷ total rules | ✅ |
| Use-case Coverage % | Rules with "Applicable Log Sources" ÷ total | ✅ |
| Quality Score | Avg of %(has description), %(has ATT&CK), %(has log source) | ✅ |
| ATLAS Coverage | No ATLAS mapping in catalog → **N/A** | ❌ |

**MITRE Heat-map** — tactics → techniques from the catalog's ATT&CK columns; tactic
"heat" = rules mapped to it (relative).

**Rule Effectiveness** — each catalog rule's **triggers** = XSOAR incidents whose
Rule Name / Rule ID / Rule UUID matches. Computes the **average triggers** across
triggered rules and buckets every rule:
- **Above avg** (> 1.25× avg), **Near avg** (0.75–1.25× avg), **Below avg** (>0, <0.75× avg), **Not triggered** (0).
Summary chips + a table (rule, ID, triggers, band, tactics).

**Log Source Priority pie** — counts from the Log Validation `Priority` column
(Essential / Selective / Redundant / Undefined).

---

## 6. Threat Intelligence  (`/threat-intel`)
From the Threat Intel upload: total advisories, industry breakdown, IOC/hash-type
mix, advisories timeline, top advisories. Empty (zeros) until uploaded.

## 7. SOAR / Automation  (`/soar`)
From XSOAR: automation rate, auto vs manual closures, playbook usage, throughput.

---

## 8. Comparison  (`/comparison`)
Three sub-tabs: **Weekly / Monthly / Quarterly**.
- **Take Snapshot** captures 13 live KPIs (incidents, SLA, MTTR, automation, risk,
  health, FP, advisories, MITRE coverage, detection coverage, quality, rules
  triggered, total rules) for the current tenant + period into history.
- Each new snapshot is **auto-compared with the previous** one of the same period:
  per-KPI cards show previous → current with a delta badge (▲/▼ + %), coloured by
  whether the move is good/bad. First snapshot = "baseline".
- **Snapshot History** table (newest-first, "latest" badge, who took it, delete).
- Weekly/Monthly/Quarterly histories are kept separate.

## 9. IRIS Copilot (floating)
Chat grounded on the tenant's live KPI snapshot + live XSOAR (noisy rules / top
rules). Answers e.g. "which rule has the highest FP rate?". Uses a **self-hosted
Ollama** model when deployed via Docker; falls back to a deterministic rule-based
engine (as in this preview).

## 10. Reporting
- **PPTX export** — one-click deck of the live dashboards (empty sections render "No data").
- **Scheduled email reports** (Settings) — APScheduler weekly (Mon 08:00 UTC) /
  monthly (1st 08:00 UTC) auto-emails the PPTX; "Send now" for on-demand. Delivery is
  console-logged unless SMTP is configured.

## 11. Settings  (`/settings`)
Tenants (add / branding / QRadar-domain import), scheduled reports manager, and the
Local LLM (IRIS/Ollama) status.

---

### Notes / honest limitations
- **QRadar** ingestion isn't wired yet (files are stored only). "Offenses" and real
  asset/geo would come from a QRadar offense feed.
- **YoY** cards are currently **month-over-month** (no year of history yet).
- **ATLAS coverage** = N/A (no ATLAS mapping in the rule catalog).
- Auth: single **admin** account (demo persona users removed).
