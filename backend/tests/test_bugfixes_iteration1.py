"""Test 5 bug fixes for SOC Manager/Executive/Detection Engineering dashboards."""
import os
import io
import pytest
import requests

def _load_backend_url():
    url = os.environ.get('REACT_APP_BACKEND_URL')
    if not url:
        env_path = "/app/frontend/.env"
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
    return url.rstrip('/')

BASE_URL = _load_backend_url()
ADMIN_EMAIL = "admin@mssp-soc.io"
ADMIN_PASS = "Soc-I10eekKuxiW23Q!"

CSV_CONTENT = """id,name,severity,status,occurred,created,closed,Actual Time Taken,Rule Name,MITRE Tactic Name,MITRE Technique Name,SLA Breached,close reason
1,Suspicious PowerShell,Critical,Closed,2026-08-01T10:00:00Z,2026-08-01T10:12:00Z,2026-08-01T11:00:00Z,1800,Suspicious PowerShell Encoded Command,Execution,PowerShell,false,True Positive
2,Impossible Travel,High,Closed,2026-08-02T09:00:00Z,2026-08-02T09:05:00Z,2026-08-02T09:45:00Z,900,Impossible Travel Login,Initial Access,Valid Accounts,false,False Positive
3,Brute Force,High,Closed,2026-08-03T08:00:00Z,2026-08-03T08:20:00Z,2026-08-03T09:30:00Z,2400,Multiple Failed Logins From Same IP,Credential Access,Brute Force,true,True Positive
4,Kerberoast,Medium,Open,2026-08-04T14:00:00Z,2026-08-04T14:30:00Z,,,Kerberoast Attempt Detected,Credential Access,Kerberoasting,false,
5,Data Exfil,Critical,Closed,2026-08-05T16:00:00Z,2026-08-05T16:08:00Z,2026-08-05T17:00:00Z,3000,Outbound Data Exfil > 100MB,Exfiltration,Over C2,true,True Positive
6,Phishing Email,Low,Closed,2026-08-06T11:00:00Z,2026-08-06T11:03:00Z,2026-08-06T11:20:00Z,600,Malicious IOC Match,Initial Access,Phishing,false,False Positive
"""

CSV_ALT = """id,name,severity,status,occurred,created,closed,Actual Time Taken,Rule Name,MITRE Tactic Name,MITRE Technique Name,SLA Breached,close reason
10,Ransomware,Critical,Closed,2026-09-01T10:00:00Z,2026-09-01T10:05:00Z,2026-09-01T10:30:00Z,600,Ransomware Encrypt,Impact,Data Encrypted for Impact,false,True Positive
11,Cred Dump,High,Closed,2026-09-02T09:00:00Z,2026-09-02T09:05:00Z,2026-09-02T09:45:00Z,300,LSASS Dump,Credential Access,OS Credential Dumping,false,True Positive
"""


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


def _clear(headers):
    requests.delete(f"{BASE_URL}/api/dashboard/soc-manager/data", params={"tenant_id": "all"}, headers=headers)


def _upload(headers, content):
    files = {"file": ("incidents.csv", io.BytesIO(content.encode()), "text/csv")}
    return requests.post(
        f"{BASE_URL}/api/upload/data",
        params={"source": "xsoar", "tenant_id": "all"},
        headers=headers,
        files=files,
    )


class TestBugFixes:
    def test_00_clear_and_upload(self, headers):
        _clear(headers)
        r = _upload(headers, CSV_CONTENT)
        assert r.status_code == 200, f"upload failed {r.status_code} {r.text}"
        j = r.json()
        print("upload resp:", j)
        assert j.get("bound_rows", 0) > 0, f"bound_rows should be >0, got {j}"

    def test_01_mttd_replaces_mtta(self, headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/soc-manager", params={"tenant_id": "all"}, headers=headers)
        assert r.status_code == 200
        summary = r.json().get("summary", {})
        print("summary:", summary)
        assert "mttd_minutes" in summary
        assert summary["mttd_minutes"] is not None
        assert float(summary["mttd_minutes"]) > 0

    def test_02_detection_coverage_not_null_exec(self, headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/executive",
                         params={"tenant_id": "all", "period": "monthly"}, headers=headers)
        assert r.status_code == 200
        dc = r.json().get("detection_coverage")
        print("exec detection_coverage:", dc)
        assert dc is not None
        assert isinstance(dc, (int, float))

    def test_02b_detection_coverage_not_null_deteng(self, headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/detection-engineering",
                         params={"tenant_id": "all", "period": "monthly"}, headers=headers)
        assert r.status_code == 200
        q = r.json().get("quality", {})
        print("det-eng quality:", q)
        assert q.get("detection_coverage") is not None
        assert isinstance(q["detection_coverage"], (int, float))

    def test_03_mitre_hits_dynamic(self, headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/detection-engineering",
                         params={"tenant_id": "all", "period": "monthly"}, headers=headers)
        assert r.status_code == 200
        heatmap = r.json().get("mitre_heatmap", [])
        print("heatmap:", heatmap)
        assert isinstance(heatmap, list) and len(heatmap) > 0
        # techniques from CSV
        techs = {}
        for tactic in heatmap:
            for t in tactic.get("techniques", []):
                techs[t.get("name")] = t.get("hits")
        print("techs mapped:", techs)
        expected = ["PowerShell", "Valid Accounts", "Brute Force", "Kerberoasting", "Over C2", "Phishing"]
        found_any = all(techs.get(t, 0) == 1 for t in expected)
        assert found_any, f"No dynamic hits reflected for expected techniques. heatmap={heatmap}"

    def test_04_severity_critical_and_high(self, headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/soc-manager", params={"tenant_id": "all"}, headers=headers)
        assert r.status_code == 200
        sev = r.json().get("severity_distribution", [])
        print("severity_distribution:", sev)
        # normalize into dict
        if isinstance(sev, list):
            sev_map = {(s.get("severity") or s.get("name") or s.get("label")): (s.get("count") or s.get("value")) for s in sev}
        else:
            sev_map = sev
        print("sev_map:", sev_map)
        assert sev_map.get("Critical", 0) >= 2, f"Critical should be 2, sev_map={sev_map}"
        assert sev_map.get("High", 0) >= 2, f"High should be 2, sev_map={sev_map}"

    def test_05_mttr_not_inflated(self, headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/soc-manager", params={"tenant_id": "all"}, headers=headers)
        assert r.status_code == 200
        mttr = r.json().get("summary", {}).get("mttr_hours")
        print("mttr_hours:", mttr)
        assert mttr is not None
        assert 0 < float(mttr) < 1.0, f"mttr should be well under 1 hour, got {mttr}"

    def test_06_live_different_upload(self, headers):
        _clear(headers)
        r = _upload(headers, CSV_ALT)
        assert r.status_code == 200
        # check new heatmap
        r2 = requests.get(f"{BASE_URL}/api/dashboard/detection-engineering",
                          params={"tenant_id": "all", "period": "monthly"}, headers=headers)
        heatmap = r2.json().get("mitre_heatmap", [])
        techs = {}
        for tactic in heatmap:
            for t in tactic.get("techniques", []):
                techs[t.get("name")] = t.get("hits")
        print("alt heatmap techs:", techs)
        # Alt CSV has techniques 'Data Encrypted for Impact' and 'OS Credential Dumping'
        # Old techniques from prior upload should be gone (data is live)
        assert techs.get("PowerShell") in (None, 0), f"stale PowerShell hits: {techs}"
        assert techs.get("Brute Force") in (None, 0), f"stale Brute Force hits: {techs}"
        # severity now Critical=1, High=1
        r3 = requests.get(f"{BASE_URL}/api/dashboard/soc-manager", params={"tenant_id": "all"}, headers=headers)
        sev = r3.json().get("severity_distribution", [])
        sev_map = {(s.get("severity") or s.get("name") or s.get("label")): (s.get("count") or s.get("value")) for s in sev} if isinstance(sev, list) else sev
        print("alt sev_map:", sev_map)
        assert sev_map.get("Critical", 0) == 1
        assert sev_map.get("High", 0) == 1

    def test_99_cleanup(self, headers):
        r = requests.delete(f"{BASE_URL}/api/dashboard/soc-manager/data",
                            params={"tenant_id": "all"}, headers=headers)
        print("cleanup:", r.status_code, r.text[:200])
        assert r.status_code in (200, 204)
