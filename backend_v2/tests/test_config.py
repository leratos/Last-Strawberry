import os
import sys
import types
import unittest
from unittest.mock import Mock, patch

from backend_v2.app import config
from backend_v2.app.config import Settings


class TestConfig(unittest.TestCase):
    def test_prefers_ls_openrouter_api_key(self):
        with patch.dict(
            os.environ,
            {"LS_OPENROUTER_API_KEY": "ls-key-123", "OPENROUTER_API_KEY": "fallback-key"},
            clear=False,
        ):
            settings = Settings.from_env()
        self.assertEqual(settings.openrouter_api_key, "ls-key-123")

    def test_falls_back_to_openrouter_api_key(self):
        with patch.dict(
            os.environ,
            {"LS_OPENROUTER_API_KEY": "", "OPENROUTER_API_KEY": "fallback-key-456"},
            clear=False,
        ):
            settings = Settings.from_env()
        self.assertEqual(settings.openrouter_api_key, "fallback-key-456")

    def test_keyring_fallback(self):
        fake_keyring = types.ModuleType("keyring")

        def fake_get_password(service, username):
            if service == "OPENROUTER_API_KEY" and username == "default":
                return "keyring-secret-789"
            return None

        fake_keyring.get_password = fake_get_password

        with patch.dict(
            os.environ,
            {
                "LS_OPENROUTER_API_KEY": "",
                "OPENROUTER_API_KEY": "",
                "LS_OPENROUTER_KEYRING_SERVICE": "OPENROUTER_API_KEY",
                "LS_OPENROUTER_KEYRING_USERNAME": "default",
            },
            clear=False,
        ), patch.dict(sys.modules, {"keyring": fake_keyring}):
            settings = Settings.from_env()

        self.assertEqual(settings.openrouter_api_key, "keyring-secret-789")

    def test_windows_credential_discovery_parser(self):
        fake_output = (
            "    Ziel: LegacyGeneric:target=HomeGym_AI_Coach\n"
            "    Typ: Allgemeine\n"
            "    Benutzer: OPENROUTER_API_KEY\n"
        )
        run_mock = Mock(return_value=Mock(returncode=0, stdout=fake_output))
        with patch.object(config, "os") as os_mod, patch.object(config.subprocess, "run", run_mock):
            os_mod.name = "nt"
            services = config._discover_windows_keyring_services("OPENROUTER_API_KEY")

        self.assertEqual(services, ["HomeGym_AI_Coach"])

    def test_database_settings_from_env(self):
        with patch.dict(
            os.environ,
            {
                "LS_DATABASE_URL": "sqlite:///tmp/test.db",
                "LS_DATABASE_AUTO_INIT": "false",
            },
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.database_url, "sqlite:///tmp/test.db")
        self.assertFalse(settings.database_auto_init)


if __name__ == "__main__":
    unittest.main()
