"""Integration tests for AI Carpenter HTTP Webhook Server."""
import hashlib
import hmac
import http.client
import json
import threading
import time
import unittest

from app.config import config
from app.web import CarpenterRequestHandler, deduplicator
import http.server


class TestServerIntegration(unittest.TestCase):
    """Start local ThreadingHTTPServer on an ephemeral port and test all HTTP endpoints."""

    @classmethod
    def setUpClass(cls):
        # Bind to localhost on port 8099 for testing
        cls.port = 8099
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", cls.port), CarpenterRequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path: str):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request("GET", path)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, resp.getheaders(), data

    def _post(self, path: str, body: dict, headers: dict = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)
        json_body = json.dumps(body).encode("utf-8")
        conn.request("POST", path, body=json_body, headers=req_headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, resp.getheaders(), data

    def test_health_check(self):
        status, _, body = self._get("/health")
        self.assertEqual(status, 200)
        data = json.loads(body.decode())
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "AI Carpenter Assistant")

    def test_webhook_handshake_success(self):
        token = config.WHATSAPP_VERIFY_TOKEN
        challenge = "test_challenge_12345"
        path = f"/webhook/whatsapp?hub.mode=subscribe&hub.verify_token={token}&hub.challenge={challenge}"
        status, _, body = self._get(path)
        self.assertEqual(status, 200)
        self.assertEqual(body.decode(), challenge)

    def test_webhook_handshake_forbidden_wrong_token(self):
        path = f"/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=WRONG_TOKEN&hub.challenge=test_123"
        status, _, _ = self._get(path)
        self.assertEqual(status, 403)

    def test_webhook_post_meta_payload(self):
        meta_payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "1001",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "contacts": [{"profile": {"name": "Test User"}, "wa_id": "9998887776"}],
                        "messages": [{
                            "from": "9998887776",
                            "id": f"wamid_test_{time.time()}",
                            "timestamp": str(int(time.time())),
                            "text": {"body": "Need a solid Sheesham 6-seater dining table"},
                            "type": "text",
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }
        status, _, body = self._post("/webhook/whatsapp", meta_payload)
        self.assertEqual(status, 200)
        data = json.loads(body.decode())
        self.assertTrue(data["ok"])
        self.assertEqual(data["received"], 1)

    def test_simulator_and_carpenter_pages_served(self):
        status_sim, _, body_sim = self._get("/simulator")
        self.assertEqual(status_sim, 200)
        self.assertIn(b"Heritage Woodworks", body_sim)

        status_carp, _, body_carp = self._get("/carpenter")
        self.assertEqual(status_carp, 200)
        self.assertIn(b"Workshop Console", body_carp)


if __name__ == "__main__":
    unittest.main()
