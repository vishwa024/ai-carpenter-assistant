"""WhatsApp Outbound Messaging Bridge.

Handles sending outbound messages to customers via Meta WhatsApp Cloud API
or mock simulated channel when running in local/test mode.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

from app.config import config

logger = logging.getLogger("carpenter.whatsapp")


class WhatsAppChannel:
    """Outbound bridge for WhatsApp Cloud API and simulation dispatch."""

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

    def send_message(self, recipient_id: str, message_text: str) -> Dict[str, Any]:
        """Send a standard text message to a WhatsApp recipient.

        Args:
            recipient_id: Customer phone number in E.164 format without '+' or with digits.
            message_text: The WhatsApp formatted text response.

        Returns:
            Dict containing the API response status or simulated response.
        """
        clean_recipient = recipient_id.strip().lstrip("+")
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

        # Check if production WhatsApp API credentials are valid
        can_send_live = bool(
            config.CHANNEL == "whatsapp"
            and self.token
            and self.phone_number_id
            and self.token != "your_meta_system_user_token"
            and self.phone_number_id != "your_meta_phone_number_id"
        )

        record: Dict[str, Any] = {
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "recipient_id": clean_recipient,
            "message_text": message_text,
            "channel": "whatsapp_live" if can_send_live else "simulator",
        }

        if not can_send_live:
            # Local simulation / dry-run mode
            logger.info(
                f"[SIMULATOR OUTBOUND] To: {clean_recipient} | Text:\n{message_text}"
            )
            simulated_response = {
                "messaging_product": "whatsapp",
                "contacts": [{"input": clean_recipient, "wa_id": clean_recipient}],
                "messages": [{"id": f"wamid.SIMULATED_{int(time.time() * 1000)}"}],
                "status": "simulated",
            }
            record["response"] = simulated_response
            record["status"] = "delivered_simulated"
            self.outbound_history.append(record)
            return simulated_response

        # Live Meta Graph API POST
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "AI-Carpenter-Assistant/1.0",
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.api_url, data=data_bytes, headers=headers, method="POST")

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
