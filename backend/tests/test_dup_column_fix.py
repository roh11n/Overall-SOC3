"""Test the duplicate-column dedup fix in xsoar_ingest.parse_rows.

Regression: uploading an XSOAR CSV with duplicate-normalizing headers
(e.g. both 'occurred' and 'Occurred') used to bind 0 rows because
row.get('occurred') returned a Series, triggering a ValueError.
"""
import io
import os
import random
from datetime import datetime, timedelta, timezone

import pytest
import requests


def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    url = line.split("=", 1)[1].strip()
                    break
    return url.rstrip("/")


BASE_URL = _load_backend_url()
ADMIN_EMAIL = "admin@mssp-soc.io"
ADMIN_PASS = "Soc-I10eekKuxiW23Q!"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
    )
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {tok}"}


def _clear(headers):
    requests.delete(
        f"{BASE_URL}/api/dashboard/soc-manager/data",
        params={"tenant_id": "all"},
        headers=headers,
    )


def _upload(headers, content: str, filename: str = "incidents.csv"):
    files = {"file": (filename, io.BytesIO(content.encode()), "text/csv")}
    return requests.post(
        f"{BASE_URL}/api/upload/data",
        params={"source": "xsoar", "tenant_id": "all"},
        headers=headers,
        files=files,
    )


def _build_dup_csv(n_rows: int = 60) -> str:
    """CSV with duplicate-normalizing headers (occurred/Occurred, created/Created)."""
    header = (
        "Event ID,id,name,type,severity,AnalystSeverity,phase,L2_Owner,"
        "analystJustification,occurred,Occurred,created,Created,closed,"
        "Actual Time Taken,Log Source,MITRE Tactic Name,MITRE Technique Name,"
        "SLA Breached,close reason"
    )
    sevs = ["Critical", "High", "Medium", "Low"]
    log_sources = ["Splunk", "Sentinel", "CrowdStrike", "Defender", "Palo Alto"]
    tactics = ["Initial Access", "Execution", "Credential Access", "Exfiltration", "Impact"]
    techs = ["Phishing", "PowerShell", "Brute Force", "Over C2", "Data Encrypted for Impact"]
    reasons = ["True Positive", "False Positive", "Duplicate", "True Positive"]
    lines = [header]
    base = datetime(2026, 1, 5, 9, 0, 0, tzinfo=timezone.utc)
    for i in range(n_rows):
        occ = base + timedelta(hours=i * 3)
        det = occ + timedelta(minutes=random.randint(5, 30))
        clo = det + timedelta(minutes=random.randint(20, 240))
        sev = sevs[i % len(sevs)]
        ls = log_sources[i % len(log_sources)]
        tac = tactics[i % len(tactics)]
        te = techs[i % len(techs)]
        rn = reasons[i % len(reasons)]
        sla = "true" if i % 7 == 0 else "false"
        ttt = random.randint(600, 5400)
        lines.append(
            f"E{i+1},{1000+i},Incident {i+1},Alert,{sev},{sev},Triage,analyst{i%3},"
            f"reviewed,{occ.isoformat()},{occ.isoformat()},{det.isoformat()},"
            f"{det.isoformat()},{clo.isoformat()},{ttt},{ls},{tac},{te},{sla},{rn}"
        )
    return "\n".join(lines) + "\n"


def _build_normal_csv(n_rows: int = 10) -> str:
    header = (
        "id,name,severity,status,occurred,created,closed,Actual Time Taken,"
        "Rule Name,MITRE Tactic Name,MITRE Technique Name,SLA Breached,close reason"
    )
    lines = [header]
    base = datetime(2026, 2, 1, 8, 0, 0, tzinfo=timezone.utc)
    for i in range(n_rows):
        occ = base + timedelta(hours=i * 4)
        det = occ + timedelta(minutes=10)
        clo = det + timedelta(minutes=45)
        lines.append(
            f"{i+1},Incident {i+1},High,Closed,{occ.isoformat()},{det.isoformat()},"
            f"{clo.isoformat()},1800,Rule {i+1},Execution,PowerShell,false,True Positive"
        )
    return "\n".join(lines) + "\n"


N_DUP = 60


class TestDuplicateColumnFix:
    def test_01_upload_dup_columns_binds_all_rows(self, headers):
        _clear(headers)
        csv = _build_dup_csv(N_DUP)
        r = _upload(headers, csv, "dup_cols.csv")
        assert r.status_code == 200, f"upload failed {r.status_code} {r.text}"
        j = r.json()
        print("dup upload resp:", j)
        assert "error" not in j, f"unexpected error in response: {j}"
        assert j.get("xsoar_ingest_error") in (None, ""), f"xsoar ingest error: {j}"
        # bound_rows must equal number of data rows
        assert j.get("bound_rows") == N_DUP, (
            f"expected bound_rows={N_DUP}, got {j.get('bound_rows')}, resp={j}"
        )
        assert j.get("rows_in_file", N_DUP) == N_DUP

    def test_02_soc_manager_live_after_dup_upload(self, headers):
        r = requests.get(
            f"{BASE_URL}/api/dashboard/soc-manager",
            params={"tenant_id": "all"},
            headers=headers,
        )
        assert r.status_code == 200
        j = r.json()
        assert j.get("data_status") == "live", f"expected live, got {j.get('data_status')}"
        summary = j.get("summary", {})
        print("summary:", summary)
        assert summary.get("total_incidents") == N_DUP
        assert isinstance(summary.get("mttd_minutes"), (int, float))
        assert summary["mttd_minutes"] > 0
        assert isinstance(summary.get("mttr_hours"), (int, float))
        assert summary["mttr_hours"] > 0

    def test_03_regression_normal_csv_still_binds(self, headers):
        _clear(headers)
        csv = _build_normal_csv(10)
        r = _upload(headers, csv, "normal.csv")
        assert r.status_code == 200
        j = r.json()
        print("normal upload resp:", j)
        assert j.get("bound_rows") == 10, f"expected 10, got {j}"
        r2 = requests.get(
            f"{BASE_URL}/api/dashboard/soc-manager",
            params={"tenant_id": "all"},
            headers=headers,
        )
        assert r2.status_code == 200
        assert r2.json().get("data_status") == "live"

    def test_04_pptx_export_still_valid(self, headers):
        # Re-upload dup CSV and hit PPTX
        _clear(headers)
        csv = _build_dup_csv(N_DUP)
        r = _upload(headers, csv, "dup_cols.csv")
        assert r.status_code == 200
        r2 = requests.get(
            f"{BASE_URL}/api/export/pptx",
            params={"tenant_id": "all", "period": "quarterly"},
            headers=headers,
        )
        assert r2.status_code == 200, f"pptx failed {r2.status_code} {r2.text[:200]}"
        # PPTX starts with PK zip signature
        assert r2.content[:2] == b"PK", "pptx not a valid zip file"
        # verify 9 slides
        import zipfile
        with zipfile.ZipFile(io.BytesIO(r2.content)) as z:
            slides = [n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
            print(f"pptx slide count: {len(slides)}")
            assert len(slides) == 9, f"expected 9 slides, got {len(slides)}"

    def test_99_cleanup(self, headers):
        r = requests.delete(
            f"{BASE_URL}/api/dashboard/soc-manager/data",
            params={"tenant_id": "all"},
            headers=headers,
        )
        assert r.status_code in (200, 204)
