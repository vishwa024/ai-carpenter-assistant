"""WhatsApp Outbound Messaging Bridge.

Handles sending outbound messages to customers via Meta WhatsApp Cloud API
or simulated/WhatsApp Web deep links when running in local/test mode.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request

from app.config import config

logger = logging.getLogger("carpenter.whatsapp")

WHATSAPP_WEB_URL = "https://web.whatsapp.com"


class WhatsAppChannel:
    """Outbound bridge for WhatsApp Cloud API and WhatsApp Web simulation dispatch."""

    def __init__(
        self,
        token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        graph_version: str = "v20.0",
    ) -> None:
        self.token = token or config.WHATSAPP_TOKEN
        self.phone_number_id = phone_number_id or config.WHATSAPP_PHONE_NUMBER_ID
        self.graph_version = graph_version
        # In-memory message store for simulation and dashboard inspection
        self.outbound_history: List[Dict[str, Any]] = []

    @property
    def api_url(self) -> str:
        """Meta WhatsApp Cloud API endpoint."""
        return f"https://graph.facebook.com/{self.graph_version}/{self.phone_number_id}/messages"

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
        """Send a message to a WhatsApp recipient.

        If Meta Cloud API credentials (WHATSAPP_TOKEN & WHATSAPP_PHONE_NUMBER_ID) are set,
        it dispatches an automated message via Meta Graph API.
        Otherwise, it logs the message and generates a WhatsApp Web deep link for simulation.

        Args:
            recipient_id: Customer phone number.
            message_text: The WhatsApp formatted text response.

        Returns:
            Dict containing the API response status or simulated response.
        """
        clean_recipient = recipient_id.strip().lstrip("+").replace(" ", "").replace("-", "")
        deep_link = self.get_chat_deep_link(clean_recipient)

        # Re-read credentials from config in case they were updated at runtime
        token = self.token or config.WHATSAPP_TOKEN
        phone_number_id = self.phone_number_id or config.WHATSAPP_PHONE_NUMBER_ID

        # Determine whether live Meta WhatsApp API can be called
        can_send_live = bool(
            token
            and phone_number_id
            and token != "your_meta_system_user_token"
            and phone_number_id != "your_meta_phone_number_id"
            and (config.CHANNEL == "whatsapp" or config.is_whatsapp_configured)
        )

        record: Dict[str, Any] = {
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "recipient_id": clean_recipient,
            "message_text": message_text,
            "channel": "whatsapp_live" if can_send_live else "whatsapp_web",
            "deep_link": deep_link,
        }

        if not can_send_live:
            # Local / Web simulation mode
            logger.info(
                f"[WHATSAPP WEB / SIMULATOR] To: {clean_recipient} | Open: {deep_link} | Text:\n{message_text}"
            )
            simulated_response = {
                "messaging_product": "whatsapp",
                "contacts": [{"input": clean_recipient, "wa_id": clean_recipient}],
                "messages": [{"id": f"wamid.SIMULATED_{int(time.time() * 1000)}"}],
                "status": "whatsapp_web",
                "deep_link": deep_link,
            }
            record["response"] = simulated_response
            record["status"] = "ready_for_whatsapp_web"
            self.outbound_history.append(record)
            return simulated_response

        # Live Meta Graph API POST
        api_endpoint = f"https://graph.facebook.com/{self.graph_version}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_recipient,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message_text,
            },
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "AI-Carpenter-Assistant/1.0",
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(api_endpoint, data=data_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                resp_body = resp.read().decode("utf-8")
                resp_json = json.loads(resp_body) if resp_body else {}
                record["response"] = resp_json
                record["status"] = "delivered_live"
                self.outbound_history.append(record)
                logger.info(f"[META CLOUD API SUCCESS] To: {clean_recipient} | Status: {resp.status}")
                return resp_json
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"[META CLOUD API ERROR] Code: {e.code} | Reason: {e.reason} | Body: {err_body}")
            error_response = {
                "error": True,
                "status_code": e.code,
                "reason": e.reason,
                "details": err_body,
            }
            record["response"] = error_response
            record["status"] = "failed"
            self.outbound_history.append(record)
            return error_response
        except Exception as ex:
            logger.error(f"[META CLOUD API EXCEPTION] {ex}", exc_info=True)
            ex_response = {"error": True, "details": str(ex)}
            record["response"] = ex_response
            record["status"] = "exception"
            self.outbound_history.append(record)
            return ex_response

    def get_recent_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent outbound messages for UI inspection."""
        return self.outbound_history[-limit:]


# Global singleton instance
whatsapp_channel = WhatsAppChannel()
