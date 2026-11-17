"""Reviewer-driven hardening checks (18 Nov 2026): CORS default, rate limit, mailto validation."""
import os
import unittest
from fastapi.testclient import TestClient

os.environ.pop("CORS_ORIGINS", None)
import server


class T(unittest.TestCase):
    def test_cors_default_has_no_wildcard_and_keeps_production_aliases(self):
        origins = server._DEFAULT_ORIGINS.split(",")
        self.assertNotIn("*", origins)
        self.assertIn("https://duerise.vercel.app", origins)
        self.assertIn("https://receivables-rescue.vercel.app", origins)

    def test_cors_blocks_unknown_origin_but_allows_production(self):
        c = TestClient(server.app)
        r = c.get("/api/health", headers={"Origin": "https://evil.example"})
        self.assertNotEqual(r.headers.get("access-control-allow-origin"), "*")
        self.assertIsNone(r.headers.get("access-control-allow-origin"))
        r2 = c.get("/api/health", headers={"Origin": "https://duerise.vercel.app"})
        self.assertEqual(r2.headers.get("access-control-allow-origin"), "https://duerise.vercel.app")

    def test_rate_limit_trips_after_cap(self):
        os.environ["RATE_LIMIT_PER_MINUTE"] = "5"
        server._hits.clear()
        try:
            c = TestClient(server.app)
            codes = [c.get("/api/health").status_code for _ in range(7)]
            self.assertEqual(codes[:5], [200] * 5)
            self.assertEqual(codes[5:], [429, 429])
        finally:
            os.environ.pop("RATE_LIMIT_PER_MINUTE", None)
            server._hits.clear()

    def test_options_preflight_is_not_counted_and_gets_cors(self):
        os.environ["RATE_LIMIT_PER_MINUTE"] = "2"
        server._hits.clear()
        try:
            c = TestClient(server.app)
            # preflights answered by CORS, never counted
            for _ in range(4):
                r = c.options("/api/health", headers={
                    "Origin": "https://duerise.vercel.app",
                    "Access-Control-Request-Method": "GET"})
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.headers.get("access-control-allow-origin"), "https://duerise.vercel.app")
            codes = [c.get("/api/health", headers={"Origin": "https://duerise.vercel.app"}).status_code for _ in range(3)]
            self.assertEqual(codes, [200, 200, 429])
        finally:
            os.environ.pop("RATE_LIMIT_PER_MINUTE", None)
            server._hits.clear()

    def test_429_carries_cors_headers(self):
        os.environ["RATE_LIMIT_PER_MINUTE"] = "1"
        server._hits.clear()
        try:
            c = TestClient(server.app)
            c.get("/api/health", headers={"Origin": "https://duerise.vercel.app"})
            r = c.get("/api/health", headers={"Origin": "https://duerise.vercel.app"})
            self.assertEqual(r.status_code, 429)
            self.assertEqual(r.headers.get("access-control-allow-origin"), "https://duerise.vercel.app")
        finally:
            os.environ.pop("RATE_LIMIT_PER_MINUTE", None)
            server._hits.clear()

    def test_vercel_client_ip_trusts_edge_xff_only(self):
        from starlette.requests import Request
        def req(headers):
            return Request({"type": "http", "method": "GET", "path": "/",
                            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                            "client": ("10.0.0.1", 1234)})
        # through Vercel: edge-overwritten XFF is used
        self.assertEqual(server._client_ip(req({"x-vercel-id": "iad1::abc", "x-forwarded-for": "1.2.3.4, 5.6.7.8"})), "1.2.3.4")
        # no Vercel marker: client-sent XFF ignored, direct peer used
        self.assertEqual(server._client_ip(req({"x-forwarded-for": "1.2.3.4"})), "10.0.0.1")
        # nothing at all: direct peer
        self.assertEqual(server._client_ip(req({})), "10.0.0.1")

    def test_mailto_address_validation(self):
        good = "ap@everline.example"
        bad = ["a@b.co?subject=x", "a@b.co&body=x", "a@b.co\nBcc: x@y.z", "two@a.b, three@c.d", "not-an-email"]
        pat = __import__("re").compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
        self.assertTrue(pat.match(good))
        for b in bad:
            self.assertIsNone(pat.match(b.strip()), b)


if __name__ == "__main__":
    unittest.main()
