"""APScheduler-driven automated PPTX email reports.

Weekly (Mon 08:00 UTC) and monthly (1st 08:00 UTC) cron jobs scan
`db.report_schedules` for enabled entries and email each one a freshly-built
PPTX deck via the existing emailer (console-mock unless SMTP_* env is set).
"""
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import emailer
import llm as llm_mod
import pptx_export
import recommendations
import rules_ingest
import tenants as tenants_mod
import ti_ingest
import xsoar_ingest

logger = logging.getLogger("mssp-soc.scheduler")

_scheduler = None


async def _get_tenant(db, tenant_id):
    t = await db.tenants.find_one({"id": tenant_id or "all"}, {"_id": 0})
    if not t:
        return {"id": "all", "name": "All Tenants", "domain": "ALL", "primary_color": "#3B82F6", "logo_url": None}
    return t


async def build_bundle(db, period: str, tenant_id: str):
    """Assemble the dashboards bundle + recommendations for PPTX/email, using
    LIVE uploads (XSOAR + TI) where available and blank templates otherwise."""
    tenant = await _get_tenant(db, tenant_id)
    all_data = tenants_mod.all_dashboards(period, tenant)

    roll = await xsoar_ingest.compute_executive_rollup(db, tenant_id)
    overlay = await xsoar_ingest.compute_detection_overlay(db, tenant_id)
    ti = await ti_ingest.compute_dashboard(db, tenant_id=tenant_id, period=period)
    has_x = roll.get("data_status") == "live"
    has_ti = ti.get("data_status") == "live"

    if has_x or has_ti:
        sla = roll.get("sla_compliance") or 0
        fp = roll.get("false_positive_rate") or 0
        auto = roll.get("automation_rate") or 0
        mttr = roll.get("mttr_hours") or 0
        det_cov = overlay.get("mitre_coverage") if overlay.get("data_status") == "live" else 0
        ex = all_data["executive"]
        ex.update({
            "data_status": "live",
            "health_score": round(max(0.0, min(100.0, 0.5 * sla + 0.3 * auto + 0.2 * det_cov)), 1),
            "risk_score": round(max(0.0, min(100.0, 0.5 * fp + 0.3 * (100 - sla) + 0.2 * min(100, mttr))), 1),
            "incidents": roll.get("incidents") or 0,
            "sla_compliance": sla, "mttr_hours": mttr,
            "detection_coverage": det_cov, "automation_rate": auto,
            "advisories": ti["summary"]["total_advisories"] if has_ti else 0,
            "false_positive_rate": fp,
            "incident_trend": roll.get("incident_trend") or [],
            "sla_trend": roll.get("sla_trend") or [],
            "top_rule": roll.get("top_rule"), "top_mitre_tactic": roll.get("top_mitre_tactic"),
            "top_threat_actor": roll.get("top_mitre_tactic") or "—", "top_targeted_asset": "—",
        })

    if overlay.get("data_status") == "live" and overlay.get("mitre_heatmap"):
        det = all_data["detection"]
        det["data_status"] = "live"
        det["mitre_heatmap"] = overlay["mitre_heatmap"]
        det["rules"] = overlay["rules"]
        det["gap_analysis"]["techniques_covered"] = overlay["techniques_covered"]
        det["quality"]["mitre_coverage"] = overlay["mitre_coverage"]

    recs = recommendations.generate(all_data["executive"])
    recs = llm_mod.enrich_recommendations(recs, all_data["executive"], max_llm=2)

    # Live data for the QBR-style deck (Executive + Incident Monitoring).
    all_data["soc_live"] = await xsoar_ingest.compute_soc_manager(db, tenant_id)
    all_data["qbr"] = await xsoar_ingest.compute_qbr(db, tenant_id)
    all_data["ti_live"] = ti if has_ti else {"data_status": "empty"}
    _rc = await rules_ingest.latest_upload(db, tenant_id)
    all_data["rules_count"] = (_rc or {}).get("row_count")
    return tenant, all_data, recs


async def _send_one(db, sch: dict) -> dict:
    period = sch.get("period", "monthly")
    tenant_id = sch.get("tenant_id", "all")
    tenant, all_data, recs = await build_bundle(db, period, tenant_id)
    buf = pptx_export.build_pptx(tenant, period, all_data, recs)

    subject = sch.get("subject") or f"MSSP SOC Report — {tenant.get('name', 'All Tenants')} ({period})"
    html = (
        f"<p>Automated <b>{sch.get('frequency')}</b> SOC KPI report for "
        f"<b>{tenant.get('name', 'All Tenants')}</b> ({period}).</p>"
        f"<p>The PPTX deck is attached. Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.</p>"
    )
    res = await emailer.send_email(
        db,
        to=list(sch.get("recipients", [])),
        subject=subject,
        html=html,
        attachments=[{"filename": f"MSSP_SOC_{tenant.get('id', 'all')}_{period}.pptx", "data": buf.getvalue()}],
        meta={"scheduled": True, "schedule_id": sch.get("id"), "frequency": sch.get("frequency"),
              "tenant_id": tenant_id, "period": period},
    )
    await db.report_schedules.update_one(
        {"id": sch.get("id")},
        {"$set": {"last_run": datetime.now(timezone.utc).isoformat(), "last_status": res.get("mode")}},
    )
    logger.info("Scheduled report sent: schedule=%s tenant=%s mode=%s", sch.get("id"), tenant_id, res.get("mode"))
    return res


async def _run_due(db, frequency: str):
    schedules = await db.report_schedules.find(
        {"enabled": True, "frequency": frequency}
    ).to_list(500)
    logger.info("Running %d %s report schedule(s)", len(schedules), frequency)
    for sch in schedules:
        try:
            await _send_one(db, sch)
        except Exception:
            logger.exception("Scheduled report failed for schedule %s", sch.get("id"))


async def run_now(db, schedule_id: str) -> dict:
    """Trigger a single schedule immediately (used by the run-now endpoint)."""
    sch = await db.report_schedules.find_one({"id": schedule_id})
    if not sch:
        raise ValueError("Schedule not found")
    return await _send_one(db, sch)


def start(db):
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_due, CronTrigger(day_of_week="mon", hour=8, minute=0),
        args=[db, "weekly"], id="weekly_reports", replace_existing=True,
    )
    _scheduler.add_job(
        _run_due, CronTrigger(day=1, hour=8, minute=0),
        args=[db, "monthly"], id="monthly_reports", replace_existing=True,
    )
    _scheduler.start()
    logger.info("Report scheduler started (weekly Mon 08:00 UTC, monthly 1st 08:00 UTC)")
    return _scheduler


def shutdown():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
