import importlib
import logging
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


class _NoopFileHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def emit(self, record):
        return


class TestBackendV2BridgeMode(unittest.TestCase):
    @staticmethod
    def _install_google_auth_stubs_if_missing():
        try:
            import google.oauth2.id_token  # noqa: F401
            import google.auth.transport.requests  # noqa: F401
            return
        except Exception:
            pass

        google_module = sys.modules.setdefault("google", types.ModuleType("google"))
        oauth2_module = sys.modules.setdefault("google.oauth2", types.ModuleType("google.oauth2"))
        id_token_module = sys.modules.setdefault("google.oauth2.id_token", types.ModuleType("google.oauth2.id_token"))
        auth_module = sys.modules.setdefault("google.auth", types.ModuleType("google.auth"))
        transport_module = sys.modules.setdefault("google.auth.transport", types.ModuleType("google.auth.transport"))
        requests_module = sys.modules.setdefault("google.auth.transport.requests", types.ModuleType("google.auth.transport.requests"))

        id_token_module.fetch_id_token = lambda _request, _audience: "stub-token"
        requests_module.Request = object

        google_module.oauth2 = oauth2_module
        google_module.auth = auth_module
        oauth2_module.id_token = id_token_module
        auth_module.transport = transport_module
        transport_module.requests = requests_module

    @staticmethod
    def _install_auth_utils_stub_if_missing():
        if "server_tools.auth_utils" in sys.modules:
            return
        auth_utils_module = types.ModuleType("server_tools.auth_utils")
        auth_utils_module.verify_password = lambda plain_password, hashed_password: True
        auth_utils_module.get_password_hash = lambda password: f"hashed::{password}"
        auth_utils_module.create_access_token = lambda data: "stub-access-token"
        auth_utils_module.verify_access_token = lambda token: {"sub": "stub-user"}
        auth_utils_module.get_current_user_from_token = (
            lambda token: {"user_id": 7, "username": "bridge-user", "roles": ["admin"], "is_active": True}
        )
        sys.modules["server_tools.auth_utils"] = auth_utils_module

    @staticmethod
    def _install_multipart_stub_if_missing():
        try:
            import python_multipart  # noqa: F401
            import multipart  # noqa: F401
            import multipart.multipart  # noqa: F401
            return
        except Exception:
            pass

        python_multipart_module = sys.modules.setdefault("python_multipart", types.ModuleType("python_multipart"))
        python_multipart_module.__version__ = "0.0.20"

        multipart_module = sys.modules.setdefault("multipart", types.ModuleType("multipart"))
        multipart_submodule = sys.modules.setdefault("multipart.multipart", types.ModuleType("multipart.multipart"))
        multipart_module.__version__ = "0.0.20"
        multipart_submodule.parse_options_header = lambda value: (value, {})
        multipart_module.multipart = multipart_submodule

    @classmethod
    def setUpClass(cls):
        cls._install_google_auth_stubs_if_missing()
        cls._install_auth_utils_stub_if_missing()
        cls._install_multipart_stub_if_missing()

        if "backend_server.main" in sys.modules:
            cls.backend_main = sys.modules["backend_server.main"]
        else:
            with patch("logging.FileHandler", _NoopFileHandler):
                cls.backend_main = importlib.import_module("backend_server.main")

        cls.backend_main.app.router.on_startup.clear()
        cls.backend_main.app.router.on_shutdown.clear()
        cls.backend_main.app.dependency_overrides[cls.backend_main.get_current_active_user] = (
            lambda: {"user_id": 7, "username": "bridge-user", "roles": ["admin"], "is_active": True}
        )
        cls.client = TestClient(cls.backend_main.app)

    @classmethod
    def tearDownClass(cls):
        cls.backend_main.app.dependency_overrides.clear()

    def test_worlds_endpoint_uses_v2_bridge_shape(self):
        worlds_payload = [
            {"id": 4, "name": "Bridge World", "created_at": "2026-02-20T20:00:00Z"},
        ]
        with patch.object(self.backend_main, "_should_use_v2_bridge", return_value=True), patch.object(
            self.backend_main,
            "_v2_login_for_user",
            AsyncMock(return_value="v2-token"),
        ), patch.object(
            self.backend_main,
            "_v2_request",
            AsyncMock(return_value=worlds_payload),
        ):
            response = self.client.get("/worlds")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["worlds"]), 1)
        self.assertEqual(body["worlds"][0]["world_id"], 4)
        self.assertEqual(body["worlds"][0]["player_id"], 7)

    def test_create_world_endpoint_uses_v2_bridge(self):
        with patch.object(self.backend_main, "_should_use_v2_bridge", return_value=True), patch.object(
            self.backend_main,
            "_v2_login_for_user",
            AsyncMock(return_value="v2-token"),
        ), patch.object(
            self.backend_main,
            "_v2_request",
            AsyncMock(return_value={"id": 11, "name": "Neu"}),
        ):
            response = self.client.post(
                "/worlds/create",
                json={
                    "world_name": "Neu",
                    "lore": "Lore",
                    "char_name": "Held",
                    "backstory": "Backstory",
                    "attributes": {"Strength": 10},
                    "template_key": "system_fantasy",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["world_id"], 11)
        self.assertEqual(body["player_id"], 7)
        self.assertIn("Willkommen", body["initial_story"])

    def test_command_endpoint_uses_v2_bridge(self):
        with patch.object(self.backend_main, "_should_use_v2_bridge", return_value=True), patch.object(
            self.backend_main,
            "_v2_login_for_user",
            AsyncMock(return_value="v2-token"),
        ), patch.object(
            self.backend_main,
            "_v2_request",
            AsyncMock(
                return_value={
                    "narrative": "Die Szene geht weiter.",
                    "extracted_commands": [{"command": "PLAYER_MOVE"}],
                    "provider": "openrouter",
                    "models": {"analysis": "a", "narrative": "b"},
                }
            ),
        ):
            response = self.client.post(
                "/command",
                json={"command": "Ich gehe vor.", "world_id": 4, "player_id": 7},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["event_type"], "STORY")
        self.assertEqual(body["response"], "Die Szene geht weiter.")

    def test_load_game_summary_uses_v2_bridge(self):
        with patch.object(self.backend_main, "_should_use_v2_bridge", return_value=True), patch.object(
            self.backend_main,
            "_v2_login_for_user",
            AsyncMock(return_value="v2-token"),
        ), patch.object(
            self.backend_main,
            "_v2_request",
            AsyncMock(return_value=[{"narrative": "Neueste"}, {"narrative": "Aeltere"}]),
        ):
            response = self.client.get("/load_game_summary", params={"world_id": 4, "player_id": 7})

        self.assertEqual(response.status_code, 200)
        self.assertIn("Aeltere", response.json()["response"])
        self.assertIn("Neueste", response.json()["response"])

    def test_should_use_v2_bridge_false_when_canary_zero(self):
        with patch.dict(
            os.environ,
            {
                "LS_V2_BRIDGE_ENABLED": "true",
                "LS_V2_BRIDGE_CANARY_PERCENT": "0",
                "LS_V2_BRIDGE_CANARY_FORCE_USER_IDS": "",
            },
            clear=False,
        ):
            result = self.backend_main._should_use_v2_bridge({"user_id": 7, "username": "bridge-user"})
        self.assertFalse(result)

    def test_should_use_v2_bridge_true_when_forced_user(self):
        with patch.dict(
            os.environ,
            {
                "LS_V2_BRIDGE_ENABLED": "true",
                "LS_V2_BRIDGE_CANARY_PERCENT": "0",
                "LS_V2_BRIDGE_CANARY_FORCE_USER_IDS": "7, 99",
            },
            clear=False,
        ):
            result = self.backend_main._should_use_v2_bridge({"user_id": 7, "username": "bridge-user"})
        self.assertTrue(result)

    def test_should_use_v2_bridge_is_sticky_for_same_user(self):
        with patch.dict(
            os.environ,
            {
                "LS_V2_BRIDGE_ENABLED": "true",
                "LS_V2_BRIDGE_CANARY_PERCENT": "50",
                "LS_V2_BRIDGE_CANARY_FORCE_USER_IDS": "",
            },
            clear=False,
        ):
            first = self.backend_main._should_use_v2_bridge({"user_id": 4242, "username": "bridge-user"})
            second = self.backend_main._should_use_v2_bridge({"user_id": 4242, "username": "bridge-user"})
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
