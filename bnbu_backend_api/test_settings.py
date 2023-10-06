"""Offline regression configuration; never use this as a deployment settings module."""
SECRET_KEY = "isolated-regression-test-key-not-for-deployment"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
ROOT_URLCONF = "bnbu_backend_api.urls"
AUTH_USER_MODEL = "accounts.CustomUser"
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.admin", "rest_framework", "accounts", "lease", "regulations", "rental"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
MIDDLEWARE = ["django.contrib.sessions.middleware.SessionMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware"]
TEMPLATES = [{"BACKEND":"django.template.backends.django.DjangoTemplates","APP_DIRS":True,"OPTIONS":{"context_processors":["django.template.context_processors.request","django.contrib.auth.context_processors.auth","django.contrib.messages.context_processors.messages"]}}]
REST_FRAMEWORK = {"DEFAULT_AUTHENTICATION_CLASSES":["rest_framework_simplejwt.authentication.JWTAuthentication"],"DEFAULT_PAGINATION_CLASS":"rest_framework.pagination.PageNumberPagination","PAGE_SIZE":10}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default":{"BACKEND":"django.core.cache.backends.locmem.LocMemCache"}}
ENABLE_DOCUMENT_UPLOADS = False
OPENAI_API_KEY = ""

AIRDNA_URL = ""
AIRDNA_API_KEY = ""
