"""Verify upload/data returns bound_rows/dashboard/warning correctly."""
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@mssp-soc.io"
ADMIN_PASSWORD = "Admin@2026!"
TENANT = "globalbank"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


def _upload(client, source, path):
    with open(path, "rb") as fh:
        files = {"file": (os.path.basename(path), fh,
                          "application/octet-stream")}
        r = client.post(
            f"{BASE_URL}/api/upload/data?source={source}&tenant_id={TENANT}",
            files=files, timeout=60,
        )
    return r


def test_qradar_upload_bound_zero_with_warning(client):
    r = _upload(client, "qradar", "/tmp/xsoar_sample.csv")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bound_rows"] == 0
    assert data["dashboard"] is None
    assert "warning" in data and "QRadar" in data["warning"]
    assert data["bound_tenant_id"] == TENANT


def test_xsoar_happy_path(client):
    # clean first
    client.delete(f"{BASE_URL}/api/dashboard/soc-manager/data?tenant_id={TENANT}")
    r = _upload(client, "xsoar", "/tmp/xsoar_sample.csv")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bound_rows"] == 2, data
    assert data.get("warning") is None
    assert "SOC" in data["dashboard"]
    # verify soc-manager returns live
    soc = client.get(f"{BASE_URL}/api/dashboard/soc-manager?tenant_id={TENANT}").json()
    assert soc.get("data_status") == "live", soc


def test_ti_happy_path(client):
    client.delete(f"{BASE_URL}/api/dashboard/threat-intel/data?tenant_id={TENANT}")
    r = _upload(client, "threat_intel", "/tmp/ti_sample.xlsx")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bound_rows"] >= 1
    assert data.get("warning") is None
    assert data["dashboard"] == "Threat Intelligence"
    ti = client.get(f"{BASE_URL}/api/dashboard/threat-intel?tenant_id={TENANT}").json()
    assert ti.get("data_status") == "live", ti
    assert ti["summary"]["total_advisories"] >= 1


def test_ti_welspun_real_file(client):
    """Verify the real user file (multi-sheet, 'Name' header) parses to 885 rows / 60 advisories."""
    client.delete(f"{BASE_URL}/api/dashboard/threat-intel/data?tenant_id={TENANT}")
    r = _upload(client, "threat_intel", "/tmp/welspun.xlsx")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bound_rows"] == 885, data
    assert data.get("ti_row_count") == 885, data
    assert data.get("warning") is None, data
    assert data.get("ti_ingest_error") is None, data
    assert data["dashboard"] == "Threat Intelligence"
    ti = client.get(f"{BASE_URL}/api/dashboard/threat-intel?tenant_id={TENANT}").json()
    assert ti.get("data_status") == "live", ti
    assert ti["summary"]["total_advisories"] == 60, ti["summary"]


def test_ti_bad_columns_warns(client):
    client.delete(f"{BASE_URL}/api/dashboard/threat-intel/data?tenant_id={TENANT}")
    r = _upload(client, "threat_intel", "/tmp/bad_cols.csv")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bound_rows"] == 0
    assert data.get("warning")
    assert "matched" in data["warning"].lower() or "column" in data["warning"].lower()


def test_xsoar_bad_columns_warns(client):
    client.delete(f"{BASE_URL}/api/dashboard/soc-manager/data?tenant_id={TENANT}")
    r = _upload(client, "xsoar", "/tmp/bad_cols.csv")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bound_rows"] == 0
    assert data.get("warning")


def test_cleanup(client):
    r1 = client.delete(f"{BASE_URL}/api/dashboard/soc-manager/data?tenant_id={TENANT}")
    r2 = client.delete(f"{BASE_URL}/api/dashboard/threat-intel/data?tenant_id={TENANT}")
    assert r1.status_code == 200 and r2.status_code == 200
