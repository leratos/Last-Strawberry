import unittest

from starlette.requests import Request

from backend_v2.app.main import ERROR_CATEGORY_HEADER, _maybe_reject_request_body


def _build_request(method: str, body: bytes, headers: dict[str, str] | None = None) -> Request:
    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode("ascii"), value.encode("ascii")))

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": "/v2/auth/login",
        "raw_path": b"/v2/auth/login",
        "query_string": b"",
        "headers": raw_headers,
        "client": ("testclient", 123),
        "server": ("testserver", 80),
    }

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


class TestRequestBodyLimitHelpers(unittest.IsolatedAsyncioTestCase):
    async def test_skips_non_body_methods(self):
        request = _build_request("GET", b"")
        response = await _maybe_reject_request_body(request, max_body_bytes=64)
        self.assertIsNone(response)

    async def test_rejects_invalid_content_length_header(self):
        request = _build_request(
            "POST",
            b'{"user_id":1,"username":"alice"}',
            headers={"content-type": "application/json", "content-length": "invalid"},
        )
        response = await _maybe_reject_request_body(request, max_body_bytes=128)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get(ERROR_CATEGORY_HEADER), "security")

    async def test_rejects_when_declared_length_is_over_limit(self):
        request = _build_request(
            "POST",
            b'{"user_id":1,"username":"alice"}',
            headers={"content-type": "application/json", "content-length": "4096"},
        )
        response = await _maybe_reject_request_body(request, max_body_bytes=128)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.headers.get(ERROR_CATEGORY_HEADER), "security")

    async def test_rejects_when_actual_body_is_over_limit(self):
        request = _build_request(
            "POST",
            b"x" * 256,
            headers={"content-type": "application/json"},
        )
        response = await _maybe_reject_request_body(request, max_body_bytes=128)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 413)

    async def test_allows_and_restores_body_when_within_limit(self):
        body = b'{"user_id":1,"username":"alice"}'
        request = _build_request(
            "POST",
            body,
            headers={"content-type": "application/json", "content-length": str(len(body))},
        )
        response = await _maybe_reject_request_body(request, max_body_bytes=2048)
        self.assertIsNone(response)

        replayed = await request.body()
        self.assertEqual(replayed, body)


if __name__ == "__main__":
    unittest.main()
