"""WhatsApp Web Bridge.

Provides direct browser access to WhatsApp Web and wa.me deep links
instead of Meta WhatsApp Cloud API integration.
"""
from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from app.config import config

logger = logging.getLogger("carpenter.whatsapp")

WHATSAPP_WEB_URL = "https://web.whatsapp.com"


class WhatsAppChannel:
    """Bridge for WhatsApp Web direct browser access and simulation dispatch."""

    def __init__(self) -> None:
        # In-memory message store for simulation and dashboard inspection
        self.outbound_history: List[Dict[str, Any]] = []

    @staticmethod
    def get_web_url() -> str:
        """Return the WhatsApp Web URL for direct browser access."""
        return WHATSAPP_WEB_URL

    @staticmethod
    def get_chat_deep_link(phone: str, prefill_text: str = "") -> str:
        """Generate a wa.me deep link to start a WhatsApp chat with a phone number.

        Args:
            phone: Phone number in E.164 format (digits only, with country code).
            prefill_text: Optional message text to pre-fill in the chat box.

        Returns:
            URL string like https://wa.me/919876543210?text=Hello
        """
        clean_phone = phone.strip().lstrip("+").replace(" ", "").replace("-", "")
        base = f"https://wa.me/{clean_phone}"
        if prefill_text:
            # Percent-encode the message text for use in a URL query string
            base += f"?text={urllib.parse.quote(prefill_text, safe='')}"
        return base

    def send_message(self, recipient_id: str, message_text: str) -> Dict[str, Any]:
        """Record a simulated outbound message (for dashboard/testing).

        In WhatsApp Web mode, actual sending happens manually in the browser.
        This method records the intent so the dashboard can show what would be sent.

        Args:
            recipient_id: Customer phone number.
            message_text: The message text.

        Returns:
            Dict containing the simulated response with a wa.me deep link.
        """
        clean_recipient = recipient_id.strip().lstrip("+")
        record: Dict[str, Any] = {
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "recipient_id": clean_recipient,
            "message_text": message_text,
            "channel": "whatsapp_web",
            "deep_link": self.get_chat_deep_link(clean_recipient),
        }

        logger.info(
            f"[WHATSAPP WEB] To: {clean_recipient} | Open: {record['deep_link']} | Text:\n{message_text}"
        )

        simulated_response = {
            "status": "whatsapp_web",
            "deep_link": record["deep_link"],
            "message": "Open WhatsApp Web to send this message manually.",
        }
        record["response"] = simulated_response
        record["status"] = "ready_for_whatsapp_web"
        self.outbound_history.append(record)
        return simulated_response

    def get_recent_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent outbound messages for UI inspection."""
        return self.outbound_history[-limit:]


# Global singleton instance
whatsapp_channel = WhatsAppChannel()