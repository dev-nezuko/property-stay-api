import importlib
import os
from unittest import mock

from django.test import SimpleTestCase


class DeploymentSettingsTests(SimpleTestCase):
    """Load the real settings module (not test_settings) with a synthetic environment."""

    def load_settings(self, **env):
        with mock.patch.dict(os.environ, {"SECRET_KEY": "synthetic-settings-check", **env}, clear=False):
            module = importlib.import_module("bnbu_backend_api.settings")
            return importlib.reload(module)

    def test_logging_is_console_only(self):
        settings = self.load_settings()
        handlers = settings.LOGGING["handlers"].values()
        self.assertEqual({handler["class"] for handler in handlers}, {"logging.StreamHandler"})

    def test_static_files_use_whitenoise_manifest_storage(self):
        settings = self.load_settings()
        self.assertEqual(settings.STORAGES["staticfiles"]["BACKEND"],
                         "whitenoise.storage.CompressedManifestStaticFilesStorage")
        self.assertFalse(hasattr(settings, "STATICFILES_DIRS"))

    def test_allowed_hosts_come_from_the_environment(self):
        settings = self.load_settings(ALLOWED_HOSTS="api.example.test, localhost")
        self.assertEqual(settings.ALLOWED_HOSTS, ["api.example.test", "localhost"])

    def test_database_url_is_honoured(self):
        settings = self.load_settings(DATABASE_URL="postgres://demo:demo@db:5432/demo")
        self.assertEqual(settings.DATABASES["default"]["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(settings.DATABASES["default"]["HOST"], "db")
