# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/bnbu_backend_api/celery.py
from __future__ import absolute_import, unicode_literals
import os
import ssl
from celery import Celery
from django.conf import settings

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bnbu_backend_api.settings")

app = Celery("bnbu_backend_api")  # Ensure this matches the project name


# Configure Celery broker and result backend
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
USE_SSL = REDIS_URL.startswith("rediss://")

app.conf.update(
    broker_url=REDIS_URL,
    result_backend=REDIS_URL,
    broker_use_ssl=(
        {
            "ssl_cert_reqs": ssl.CERT_NONE,
        }
        if USE_SSL
        else None
    ),
    redis_backend_use_ssl=(
        {
            "ssl_cert_reqs": ssl.CERT_NONE,
        }
        if USE_SSL
        else None
    ),
    accept_content=["json"],  # Ensure compatibility
    task_serializer="json",
    result_serializer="json",
)

app.conf.broker_transport_options = {
    "socket_timeout": 30,  # Timeout for Redis operations in seconds
    "socket_connect_timeout": 30,  # Timeout for connection attempts
    "max_connections": 10,  # Limit concurrent connections
}

# Add the configuration for retrying broker connection on startup
app.conf.broker_connection_retry_on_startup = True

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
