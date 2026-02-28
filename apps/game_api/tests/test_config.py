from pathlib import Path
import os
import sys
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from apps.game_api.app.config import Settings  # noqa: E402


class TestGameApiConfig(unittest.TestCase):
    def test_cors_allow_origin_regex_defaults_to_localhost_pattern(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(
            settings.cors_allow_origin_regex,
            r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        )

    def test_cors_allow_origin_regex_can_be_overridden(self):
        with mock.patch.dict(
            os.environ,
            {
                "LS_GREENFIELD_CORS_ALLOW_ORIGIN_REGEX": r"^https://play\.last-strawberry\.com$",
            },
            clear=True,
        ):
            settings = Settings.from_env()
        self.assertEqual(
            settings.cors_allow_origin_regex,
            r"^https://play\.last-strawberry\.com$",
        )


if __name__ == "__main__":
    unittest.main()
