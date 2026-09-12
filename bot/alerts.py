"""
Instant Slack alerts, fired directly from the execution process for urgent
events (e.g. the drawdown circuit breaker). Deliberately NOT routed through
the Cowork scheduled-reporting layer -- urgent events must not wait for the
next digest.
"""
import logging

import requests

import config

logger = logging.getLogger(__name__)


def send_slack_alert(message: str) -> None:
    if not config.SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not configured; alert not sent: %s", message)
        return

    try:
        response = requests.post(
            config.SLACK_WEBHOOK_URL,
            json={"text": message},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Failed to send Slack alert: %s", message)
