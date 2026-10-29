"""Server and Webhook Layer for AI Carpenter Assistant.

Implements a robust HTTP server using Python's built-in ThreadingHTTPServer:
- WhatsApp Web direct access redirects (/whatsapp, /whatsapp/chat/<phone>)
- In-memory message deduplication with thread-safe locking
- Immediate 200 OK acknowledgment and asynchronous background AI generation
- REST endpoints for the Workshop Dashboard (/carpenter) and Customer Simulator (/simulator)
"""
from __future__ import annotations

import collections
import hashlib
import hmac
import http.server
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Deque, Dict, Optional, Set, Tuple
import urllib.parse

from app.agent import carpenter_agent
from app.config import config
from app.whatsapp import whatsapp_channel, WHATSAPP_WEB_URL

# Ensure UTF-8 output on Windows consoles to prevent cp1252 charmap encoding errors
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("carpenter.web")

BASE_DIR = Path(__file__).resolve().parent


class Deduplicator:
    """Thread-safe message deduplicator with TTL cleanup."""

    def __init__(self, ttl_seconds: float = 3600.0) -> None:
        self.ttl = ttl_seconds
        self._processed: Dict[str, float] = {}
        self._lock = threading.Lock()

    def is_duplicate(self, message_id: str) -> bool:
        """Check if message_id has already been processed and mark it as seen."""
        if not message_id:
            return False
        now = time.time()
        with self._lock:
            # Periodic prune of stale IDs
            if len(self._processed) > 1000:
                self._processed = {
                    mid: ts for mid, ts in self._processed.items() if now - ts < self.ttl
                }

            if message_id in self._processed:
                return True
            self._processed[message_id] = now
            return False


class AuditLogStore:
    """Thread-safe event log store for agent and webhook activity."""

    def __init__(self, max_records: int = 200) -> None:
        self.logs: Deque[Dict[str, Any]] = collections.deque(maxlen=max_records)
        self._lock = threading.Lock()

    def log(self, category: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        record = {
            "timestamp": time.time(),
            "time_str": time.strftime("%H:%M:%S", time.localtime()),
            "category": category,
            "message": message,
            "details": details or {},
        }
        with self._lock:
            self.logs.append(record)

    def get_recent(self, limit: int = 100) -> list[Dict[str, Any]]:
        with self._lock:
            return list(self.logs)[-limit:]


# Global runtime singletons
deduplicator = Deduplicator()
audit_logs = AuditLogStore()


def verify_hmac_signature(raw_body: bytes, signature_header: Optional[str], app_secret: str) -> bool:
    """Verify incoming X-Hub-Signature-256 header against computed HMAC SHA-256."""
    if not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False

    received_sig = signature_header[7:].strip()
    computed_sig = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(received_sig, computed_sig)


def async_process_and_reply(
    sender_phone: str,
    message_text: str,
    customer_name: Optional[str] = None,
    media_info: Optional[Dict[str, Any]] = None,
    message_id: Optional[str] = None,
) -> None:
    """Background worker to invoke Carpenter Agent and dispatch response."""
    try:
        audit_logs.log(
            "AGENT_START",
            f"Generating carpenter response for customer: {sender_phone}",
            {"message_id": message_id, "text": message_text},
        )

        agent_result = carpenter_agent.process_message(
            sender_phone=sender_phone,
            message_text=message_text,
            customer_name=customer_name,
            media_info=media_info,
        )

        reply_text = agent_result["response_text"]
        audit_logs.log(
            "AGENT_COMPLETE",
            f"Crafted response in {agent_result['latency_ms']}ms via {agent_result['source']}",
            {"reply": reply_text},
        )

        # Dispatch via Outbound Messaging Bridge
        dispatch_res = whatsapp_channel.send_message(sender_phone, reply_text)
        audit_logs.log(
            "OUTBOUND_DISPATCH",
            f"Sent reply to {sender_phone}",
            {"status": dispatch_res.get("status", "sent")},
        )
    except Exception as ex:
        logger.error(f"Error in async_process_and_reply: {ex}", exc_info=True)
        audit_logs.log("ERROR", f"Agent processing failed: {ex}")


class CarpenterRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP Request Handler for WhatsApp Webhook and Workshop Web UI."""

    server_version = "CarpenterAssistant/1.0"

    def _send_json(self, status_code: int, data: Any) -> None:
        """Send JSON response with appropriate headers."""
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Hub-Signature-256")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status_code: int, text: str, content_type: str = "text/plain") -> None:
        """Send plain text or challenge response."""
        body = text.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, file_path: Path, content_type: str = "text/html") -> None:
        """Serve a static HTML or asset file from disk."""
        if not file_path.is_file():
            self._send_text(404, f"File not found: {file_path.name}")
            return
        try:
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_text(500, f"Error reading file: {e}")

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Hub-Signature-256")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle incoming GET requests."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_params = urllib.parse.parse_qs(parsed.query)

        # 1. WhatsApp Web Direct Access Routes
        if path == "/whatsapp":
            # Redirect to WhatsApp Web in the browser
            self.send_response(302)
            self.send_header("Location", WHATSAPP_WEB_URL)
            self.end_headers()
            return

        if path.startswith("/whatsapp/chat/"):
            # Redirect to a wa.me deep link for a specific phone number.
            # Optional ?text=... pre-fills the message box in WhatsApp Web.
            phone = path.split("/whatsapp/chat/")[1].strip()
            if phone:
                prefill = query_params.get("text", [""])[0]
                deep_link = whatsapp_channel.get_chat_deep_link(phone, prefill_text=prefill)
                self.send_response(302)
                self.send_header("Location", deep_link)
                self.end_headers()
                return

        # 2. Web UI Routes
        if path in ["/", "/simulator"]:
            self._serve_file(BASE_DIR / "simulator.html")
            return
        elif path == "/carpenter":
            self._serve_file(BASE_DIR / "carpenter.html")
            return

        # 3. REST API Routes
        if path == "/api/conversations":
            sessions = carpenter_agent.sessions.get_all()
            self._send_json(200, {"ok": True, "conversations": sessions})
            return

        elif path.startswith("/api/conversations/"):
            phone = path.split("/api/conversations/")[1].strip()
            session = carpenter_agent.sessions.get(phone)
            if session:
                self._send_json(200, {"ok": True, "conversation": session.to_dict()})
            else:
                self._send_json(404, {"ok": False, "error": "Conversation not found"})
            return

        elif path == "/api/logs":
            self._send_json(200, {
                "ok": True,
                "logs": audit_logs.get_recent(),
                "outbound": whatsapp_channel.get_recent_history(),
            })
            return

        elif path == "/health":
            self._send_json(200, {
                "status": "healthy",
                "service": "AI Carpenter Assistant",
                "channel": config.CHANNEL,
                "whatsapp_configured": config.is_whatsapp_configured,
                "gemini_configured": config.is_gemini_configured,
                "app_secret_configured": config.is_app_secret_configured,
                "model": config.GEMINI_MODEL,
                "timestamp": time.time(),
            })
            return

        # Fallback 404
        self._send_text(404, "404 Not Found")

    def do_POST(self) -> None:
        """Handle incoming POST requests."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Read request body
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        except Exception as e:
            logger.error(f"Failed to read POST body: {e}")
            self._send_json(400, {"ok": False, "error": "Invalid body"})
            return

        # 1. Simulator Direct API (Synchronous simulation for the web UI)
        if path == "/api/simulate":
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception as e:
                self._send_json(400, {"ok": False, "error": f"JSON parse error: {e}"})
                return

            phone = str(payload.get("from", "9876543210"))
            text = payload.get("text", "")
            name = payload.get("name", "Customer")
            msg_id = payload.get("id", f"sim_{int(time.time() * 1000)}")

            if deduplicator.is_duplicate(msg_id):
                self._send_json(200, {"ok": True, "duplicate": True, "message": "Duplicate ignored"})
                return

            # Direct generation with full response return
            agent_result = carpenter_agent.process_message(
                sender_phone=phone,
                message_text=text,
                customer_name=name,
            )

            # Record in whatsapp channel simulation
            whatsapp_channel.send_message(phone, agent_result["response_text"])

            self._send_json(200, {
                "ok": True,
                "reply": agent_result["response_text"],
                "source": agent_result["source"],
                "latency_ms": agent_result["latency_ms"],
                "session": agent_result["session"],
            })
            return

        # 3. Manual Master Reply from Carpenter Dashboard
        if path == "/api/manual_reply":
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception as e:
                self._send_json(400, {"ok": False, "error": str(e)})
                return

            phone = str(payload.get("phone", ""))
            text = str(payload.get("text", "")).strip()
            if not phone or not text:
                self._send_json(400, {"ok": False, "error": "phone and text are required"})
                return

            session = carpenter_agent.sessions.get_or_create(phone)
            session.history.append({
                "role": "model",
                "text": text,
                "timestamp": time.time(),
                "source": "manual_carpenter_override",
            })
            session.updated_at = time.time()

            dispatch_res = whatsapp_channel.send_message(phone, text)
            audit_logs.log("MANUAL_REPLY", f"Master Carpenter sent manual message to {phone}")
            self._send_json(200, {"ok": True, "dispatch": dispatch_res})
            return

        # 4. Clear Sessions & Logs for fresh testing
        if path == "/api/reset":
            carpenter_agent.sessions.clear()
            whatsapp_channel.outbound_history.clear()
            audit_logs.log("SYSTEM_RESET", "Conversation sessions and audit logs cleared.")
            self._send_json(200, {"ok": True, "message": "All sessions reset"})
            return

        # Fallback 404
        self._send_json(404, {"ok": False, "error": "Not Found"})


def safe_print(text: str) -> None:
    """Safe print helper that gracefully handles any Windows terminal codec."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def run_server(host: Optional[str] = None, port: Optional[int] = None) -> None:
    """Run the AI Carpenter HTTP server."""
    bind_host = host or config.HOST
    bind_port = port or config.PORT
    display_host = "localhost" if bind_host in ("0.0.0.0", "") else bind_host

    server = http.server.ThreadingHTTPServer((bind_host, bind_port), CarpenterRequestHandler)
    safe_print("=" * 70)
    safe_print("  [+] HERITAGE WOODWORKS - AI MASTER CARPENTER SERVICE")
    safe_print("=" * 70)
    safe_print(f"  * Local Web Simulator   : http://{display_host}:{bind_port}/simulator")
    safe_print(f"  * Workshop Dashboard UI : http://{display_host}:{bind_port}/carpenter")
    safe_print(f"  * WhatsApp Web Access   : http://{display_host}:{bind_port}/whatsapp")
    safe_print(f"  * Server Listening on   : {bind_host}:{bind_port}")
    safe_print(f"  * Channel Mode          : {config.CHANNEL.upper()}")
    safe_print(f"  * Gemini Configured     : {config.is_gemini_configured} ({config.GEMINI_MODEL})")
    safe_print("=" * 70)
    safe_print("Tip: Open http://localhost:8000/simulator or http://localhost:8000/carpenter in Chrome!")
    safe_print("Press Ctrl+C to stop the server.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down AI Carpenter Assistant...")
        server.server_close()
        sys.exit(0)


if __name__ == "__main__":
    run_server()
