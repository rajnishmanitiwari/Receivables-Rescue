"""A non-UTF-8 request body gets a clean 422 with no raw-input echo, never a bare 500.

Covers every declared content type on the JSON endpoints, because FastAPI
parses the body by endpoint signature, not by the declared content type.
Normal invalid inputs keep their existing behavior: malformed JSON syntax is a
422, well-formed but unusable invoice text is a 422 from the parser, and a
valid minimal request still succeeds. Multipart uploads to /api/extract stay
binary-safe. Validation error payloads never echo raw input back.
"""
from fastapi.testclient import TestClient
import server

c = TestClient(server.app)

NON_UTF8 = b'\xff\xfe{"data": "Acme, INV-1, 45000, 2026-01-01"}'
CONTENT_TYPES = [
    "application/json",
    "application/json; charset=utf-8",
    "text/csv",
    "text/plain",
    None,
    "multipart/form-data; boundary=x",
]
JSON_ROUTES = ["/api/analyse", "/api/next-action"]


def test_non_utf8_body_is_clean_422_every_content_type():
    for content_type in CONTENT_TYPES:
        headers = {"content-type": content_type} if content_type else {}
        for path in JSON_ROUTES:
            r = c.post(path, content=NON_UTF8, headers=headers)
            assert r.status_code == 422, (content_type, path, r.status_code, r.text)
            assert r.json() == {"detail": "Request body must be valid UTF-8."}, (
                content_type, path, r.text)


def test_non_utf8_body_never_echoed():
    r = c.post("/api/analyse", content=NON_UTF8,
               headers={"content-type": "application/json"})
    text = r.text
    assert "Acme" not in text and "INV-1" not in text
    assert "�" not in text and "\\xff" not in text.lower()


def test_decodable_wrong_type_body_validates_without_echo():
    # UTF-8-clean but not the JSON model: a 422 that must not echo the raw body.
    r = c.post("/api/analyse", content=b"totally not json at all",
               headers={"content-type": "text/csv"})
    assert r.status_code == 422
    assert "totally not json at all" not in r.text


def test_malformed_json_still_422():
    r = c.post("/api/analyse", content=b'{not json',
               headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_unusable_invoice_text_still_422():
    r = c.post("/api/analyse", json={"data": "nothing resembling an invoice at all"})
    assert r.status_code == 422


def test_valid_minimal_analyse_still_works():
    r = c.post("/api/analyse", json={"data": "Acme, INV-1, 45000, 2026-01-01"})
    assert r.status_code == 200, r.text
    assert "report" in r.json()
