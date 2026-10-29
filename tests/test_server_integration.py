"""Integration tests for AI Carpenter HTTP Webhook Server."""
import http.client
import json
import threading
import time
import unittest

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

    def test_whatsapp_web_redirect(self):
        status, headers, _ = self._get("/whatsapp")
        self.assertEqual(status, 302)
        location = dict(headers).get("Location", "")
        self.assertEqual(location, "https://web.whatsapp.com")

    def test_whatsapp_chat_deep_link_redirect(self):
        status, headers, _ = self._get("/whatsapp/chat/9876543210")
        self.assertEqual(status, 302)
        location = dict(headers).get("Location", "")
        self.assertEqual(location, "https://wa.me/9876543210")

    def test_simulator_and_carpenter_pages_served(self):
        status_sim, _, body_sim = self._get("/simulator")
        self.assertEqual(status_sim, 200)
        self.assertIn(b"Heritage Woodworks", body_sim)

        status_carp, _, body_carp = self._get("/carpenter")
        self.assertEqual(status_carp, 200)
        self.assertIn(b"Workshop Console", body_carp)

    def test_simulate_endpoint(self):
        payload = {
            "from": "9998887776",
            "text": "Need a solid Sheesham 6-seater dining table",
            "name": "Test User",
            "id": f"sim_test_{time.time()}",
        }
        status, _, body = self._post("/api/simulate", payload)
        self.assertEqual(status, 200)
        data = json.loads(body.decode())
        self.assertTrue(data["ok"])
        self.assertIn("reply", data)


if __name__ == "__main__":
    unittest.main()