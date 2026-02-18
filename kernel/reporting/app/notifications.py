import os
import httpx
import structlog
from app.models import AnalysisSummary

logger = structlog.get_logger()

async def notify_hazard(summary: AnalysisSummary):
    """
    Sends a notification to configured webhooks if a critical hazard is detected.
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.info("no_webhook_configured", document_id=summary.document_id)
        return

    if summary.risk_score < 80:
        return

    payload = {
        "text": f"🚨 *Critical Compliance Risk Detected* 🚨\n\nDocs: `{summary.document_id}`\nScore: *{summary.risk_score}/100* (CRITICAL)\n\n*Key Risks:*\n" + 
                "\n".join([f"- {r.description} ({r.severity})" for r in summary.critical_risks])
    }

    try:
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json=payload)
            logger.info("slack_notification_sent", document_id=summary.document_id)
    except Exception as e:
        logger.error("notification_failed", error=str(e))
