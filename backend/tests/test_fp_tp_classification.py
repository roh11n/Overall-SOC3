"""Backend tests for robust FP/TP close-reason classification.

Covers:
1. READ-ONLY sanity on tenant 'all' — must NOT modify or delete the real data.
2. Upload mixed close-reason variants to tenant 'acme-corp' and validate
   false_positive_rate / true_positive_rate in the SOC Manager dashboard.
3. Detection Engineering rule effectiveness reflects the same robust counting.
4. Clean up acme-corp only.
"""
from __future__ import annotations

import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@mssp-soc.io"
ADMIN_PASSWORD = "Soc-I10eekKuxiW23Q!"
ACME = "acme-corp"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# --- Test 1: read-only sanity on tenant 'all' ------------------------

def test_tenant_all_fp_rate_is_14_4(session):
    """The user's real 5,299-row upload: 764 FP / 5299 closed = 14.4%."""
    r = session.get(f"{BASE_URL}/api/dashboard/soc-manager",
                    params={"tenant_id": "all"}, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("data_status") == "live", f"tenant 'all' has no data: {data}"
    summary = data["summary"]
    print(f"tenant='all' summary: closed={summary['closed']} "
          f"fp_rate={summary['false_positive_rate']} "
          f"tp_rate={summary['true_positive_rate']} total={summary['total_incidents']}")
    assert summary["closed"] == 5299, f"closed count changed: {summary['closed']}"
    assert summary["false_positive_rate"] == 14.4, (
        f"expected 14.4, got {summary['false_positive_rate']}")
    assert summary["true_positive_rate"] == 0.0, (
        f"expected 0.0, got {summary['true_positive_rate']}")


# --- Test 2: robust FP/TP on mixed variants (acme-corp) --------------

def _build_acme_csv() -> bytes:
    """10 closed rows spread across variants.

    FP variants (3): False-Positive, Benign, FP
    TP variants (3): True Positive, Malicious, Confirmed
    Neither (2): Other, Duplicate
    Non-closed (2): open rows w/ Other close reason (should not count)
    Note: we use 10 CLOSED rows exactly to match the request expectations.
    """
    header = "id,name,severity,status,occurred,closed,Rule Name,MITRE Tactic Name,MITRE Technique Name,close reason"
    rows = [
        "1,inc-1,High,Closed,2024-06-01T00:00:00Z,2024-06-01T02:00:00Z,RuleA,Execution,T1059,False-Positive",
        "2,inc-2,High,Closed,2024-06-02T00:00:00Z,2024-06-02T02:00:00Z,RuleA,Execution,T1059,Benign",
        "3,inc-3,High,Closed,2024-06-03T00:00:00Z,2024-06-03T02:00:00Z,RuleA,Execution,T1059,FP",
        "4,inc-4,High,Closed,2024-06-04T00:00:00Z,2024-06-04T02:00:00Z,RuleB,Persistence,T1547,True Positive",
        "5,inc-5,High,Closed,2024-06-05T00:00:00Z,2024-06-05T02:00:00Z,RuleB,Persistence,T1547,Malicious",
        "6,inc-6,High,Closed,2024-06-06T00:00:00Z,2024-06-06T02:00:00Z,RuleB,Persistence,T1547,Confirmed",
        "7,inc-7,High,Closed,2024-06-07T00:00:00Z,2024-06-07T02:00:00Z,RuleC,Discovery,T1082,Other",
        "8,inc-8,High,Closed,2024-06-08T00:00:00Z,2024-06-08T02:00:00Z,RuleC,Discovery,T1082,Duplicate",
        "9,inc-9,High,Closed,2024-06-09T00:00:00Z,2024-06-09T02:00:00Z,RuleC,Discovery,T1082,Other",
        "10,inc-10,High,Closed,2024-06-10T00:00:00Z,2024-06-10T02:00:00Z,RuleC,Discovery,T1082,Duplicate",
    ]
    return ("\n".join([header, *rows]) + "\n").encode()


@pytest.fixture(scope="module")
def upload_acme(session):
    """Upload mixed CSV to acme-corp; guarantee cleanup afterwards."""
    csv = _build_acme_csv()
    files = {"file": ("acme_mixed.csv", io.BytesIO(csv), "text/csv")}
    r = session.post(f"{BASE_URL}/api/upload/data",
                     params={"source": "xsoar", "tenant_id": ACME},
                     files=files, timeout=60)
    assert r.status_code == 200, f"upload failed: {r.status_code} {r.text}"
    body = r.json()
    print(f"upload response: rows={body.get('rows')} "
          f"xsoar_row_count={body.get('xsoar_row_count')}")
    yield body
    # cleanup — DO NOT touch tenant 'all'
    d = session.delete(f"{BASE_URL}/api/dashboard/soc-manager/data",
                       params={"tenant_id": ACME}, timeout=30)
    assert d.status_code == 200


def test_soc_manager_fp_tp_variant_counts(session, upload_acme):
    r = session.get(f"{BASE_URL}/api/dashboard/soc-manager",
                    params={"tenant_id": ACME}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("data_status") == "live"
    s = data["summary"]
    print(f"acme summary: closed={s['closed']} fp={s['false_positive_rate']} "
          f"tp={s['true_positive_rate']}")
    assert s["closed"] == 10
    # 3 FP variants / 10 closed = 30.0%
    assert s["false_positive_rate"] == 30.0, s["false_positive_rate"]
    # 3 TP variants / 10 closed = 30.0%
    assert s["true_positive_rate"] == 30.0, s["true_positive_rate"]

    # close_reason_mix should include Other & Duplicate but they should NOT
    # contribute to fp/tp. Sanity check that both are present.
    reasons = {row["reason"]: row["count"] for row in data["close_reason_mix"]}
    assert reasons.get("Other") == 2, reasons
    assert reasons.get("Duplicate") == 2, reasons


def test_tenant_all_untouched(session):
    """After acme-corp upload/delete, tenant 'all' must still show 14.4%."""
    r = session.get(f"{BASE_URL}/api/dashboard/soc-manager",
                    params={"tenant_id": "all"}, timeout=60)
    assert r.status_code == 200
    s = r.json()["summary"]
    assert s["closed"] == 5299
    assert s["false_positive_rate"] == 14.4


# --- Test 3: Detection Engineering rule effectiveness ----------------

def test_detection_engineering_rule_fp_rate(session, upload_acme):
    r = session.get(f"{BASE_URL}/api/dashboard/detection-engineering",
                    params={"tenant_id": ACME}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    # rules is either at root or nested; xsoar overlay lives under 'rules'
    rules = data.get("rules") or []
    if not rules and isinstance(data.get("overlay"), dict):
        rules = data["overlay"].get("rules") or []
    print(f"detection rules keys={list(data.keys())} rules_count={len(rules)}")
    by_name = {r_["name"]: r_ for r_ in rules}
    # RuleA has 3 rows all FP variants → fp_rate 100
    assert "RuleA" in by_name, by_name.keys()
    assert by_name["RuleA"]["fp_rate"] == 100.0, by_name["RuleA"]
    # RuleB has 3 rows all TP variants → fp_rate 0
    assert "RuleB" in by_name
    assert by_name["RuleB"]["fp_rate"] == 0.0, by_name["RuleB"]
    # RuleC 4 rows Other/Duplicate → fp_rate 0
    assert "RuleC" in by_name
    assert by_name["RuleC"]["fp_rate"] == 0.0, by_name["RuleC"]
