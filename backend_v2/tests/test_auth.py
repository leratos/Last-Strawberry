import unittest

from fastapi import HTTPException

from backend_v2.app.auth import create_access_token, decode_access_token
from backend_v2.app.config import Settings


class TestAuth(unittest.TestCase):
    def test_create_and_decode_token(self):
        settings = Settings(jwt_secret="unit-test-secret-which-is-long-enough-123", jwt_expire_minutes=60)
        token = create_access_token(user_id=42, username="alice", settings=settings)
        user = decode_access_token(token, settings)
        self.assertEqual(user.user_id, 42)
        self.assertEqual(user.username, "alice")

    def test_decode_invalid_token_raises_http_401(self):
        settings = Settings(jwt_secret="unit-test-secret-which-is-long-enough-123")
        with self.assertRaises(HTTPException) as context:
            decode_access_token("invalid.token.value", settings)
        self.assertEqual(context.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
