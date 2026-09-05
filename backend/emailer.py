"""Console/MongoDB email backend.

Logs the outgoing message to stdout AND stores it in MongoDB so the UI can
preview any previously-sent message. Ready to swap for smtplib later — just
set SMTP_HOST/SMTP_USER/SMTP_PASS in .env.
"""
import base64
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

logger = logging.getLogger("mssp-soc.email")


def _smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"))


def _send_smtp(to: list, subject: str, html: str, attachments: list):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ["SMTP_USER"]
    pwd = os.environ["SMTP_PASS"]
    from_addr = os.environ.get("SMTP_FROM", user)

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to)
    msg.attach(MIMEText(html, "html"))

    for att in attachments or []:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(att["data"])
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{att["filename"]}"')
        msg.attach(part)

    with smtplib.SMTP(host, port, timeout=15) as s:
        s.starttls()
        s.login(user, pwd)
        s.sendmail(from_addr, to, msg.as_string())


async def send_email(db, *, to: list, subject: str, html: str, attachments: list, meta: dict) -> dict:
    """Send (or console-mock) an email and persist to db.emails."""
    delivered = False
    error = None
    mode = "console"
    if _smtp_configured():
        try:
            _send_smtp(to, subject, html, attachments)
            delivered = True
            mode = "smtp"
        except Exception as e:
            error = str(e)[:200]
            logger.exception("SMTP send failed")
    else:
        logger.info("EMAIL (console-mock) to=%s subject=%s attachments=%d", to, subject, len(attachments or []))

    record = {
        "to": to,
        "subject": subject,
        "html": html,
        "attachments": [
            {"filename": a["filename"], "size": len(a["data"]),
             "content_b64": base64.b64encode(a["data"]).decode()[:120000]}  # cap ~90KB per attachment preview
            for a in (attachments or [])
        ],
        "mode": mode,
        "delivered": delivered,
        "error": error,
        "meta": meta,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.emails.insert_one(record)
    record.pop("_id", None)
    return {**record, "html": record["html"][:2000]}
