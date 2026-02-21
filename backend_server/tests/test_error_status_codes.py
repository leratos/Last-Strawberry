import importlib
import logging
import os
import sys
import types
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


class _NoopFileHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def emit(self, record):
        return


class TestBackendErrorStatusCodes(unittest.TestCase):
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
            lambda token: {"user_id": 1, "username": "stub-user", "roles": ["admin"], "is_active": True}
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

        python_multipart_module = sys.modules.setdefault(
            "python_multipart", types.ModuleType("python_multipart")
        )
        python_multipart_module.__version__ = "0.0.20"

        multipart_module = sys.modules.setdefault("multipart", types.ModuleType("multipart"))
        multipart_submodule = sys.modules.setdefault(
            "multipart.multipart", types.ModuleType("multipart.multipart")
        )
        multipart_module.__version__ = "0.0.20"

        def _parse_options_header(value):
            return value, {}

        multipart_submodule.parse_options_header = _parse_options_header
        multipart_module.multipart = multipart_submodule

    @classmethod
    def setUpClass(cls):
        cls._install_auth_utils_stub_if_missing()
        cls._install_multipart_stub_if_missing()

        if "backend_server.main" in sys.modules:
            cls.backend_main = sys.modules["backend_server.main"]
        else:
            with patch("logging.FileHandler", _NoopFileHandler):
                cls.backend_main = importlib.import_module("backend_server.main")

        # Vermeidet DB/Service-Initialisierung im Startup während der Tests.
        cls.backend_main.app.router.on_startup.clear()
        cls.backend_main.app.router.on_shutdown.clear()

        cls.backend_main.app.dependency_overrides[cls.backend_main.get_current_active_user] = (
            lambda: {"user_id": 1, "username": "test-user", "roles": ["admin"], "is_active": True}
        )
        cls.client = TestClient(cls.backend_main.app)

    @classmethod
    def tearDownClass(cls):
        cls.backend_main.app.dependency_overrides.clear()

    def test_get_last_event_keeps_404_when_event_missing(self):
        with patch.object(
            self.backend_main.db_manager,
            "get_last_event_for_world_player",
            return_value=None,
        ):
            response = self.client.get("/get_last_event", params={"world_id": 1, "player_id": 1})

        self.assertEqual(response.status_code, 404)
        self.assertIn("Kein Event", response.json().get("detail", ""))

    def test_create_world_returns_503_when_bridge_disabled(self):
        payload = {
            "world_name": "Vorhandene Welt",
            "lore": "Test-Lore",
            "char_name": "Held",
            "backstory": "Test-Backstory",
            "attributes": {"strength": 10},
            "template_key": "system_fantasy",
        }

        with patch.dict(os.environ, {"LS_V2_BRIDGE_ENABLED": "false"}, clear=False):
            response = self.client.post("/worlds/create", json=payload)

        self.assertEqual(response.status_code, 503)
        self.assertIn("decommissioned", response.json().get("detail", ""))


if __name__ == "__main__":
    unittest.main()
