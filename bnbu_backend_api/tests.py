import importlib
import os
import sys
from unittest import mock

from django.test import SimpleTestCase


class DeploymentSettingsTests(SimpleTestCase):
    """Load the real settings module (not test_settings) with a synthetic environment."""

    def load_settings(self, **env):
        with mock.patch.dict(os.environ, {"SECRET_KEY": "synthetic-settings-check", **env}, clear=False):
            # A fresh import, so attributes set by an earlier environment cannot leak through.
            sys.modules.pop("bnbu_backend_api.settings", None)
            return importlib.import_module("bnbu_backend_api.settings")

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

    def test_deployed_environments_enforce_https_cookies(self):
        settings = self.load_settings(ENVIRONMENT="production", DATABASE_URL="postgres://demo:demo@db:5432/demo")
        self.assertTrue(settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE)
        self.assertTrue(settings.SECURE_SSL_REDIRECT)
        self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_development_does_not_redirect_to_https(self):
        settings = self.load_settings(ENVIRONMENT="development")
        self.assertFalse(getattr(settings, "SECURE_SSL_REDIRECT", False))
