from __future__ import absolute_import, unicode_literals

# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from bnbu_backend_api.celery import app as celery_app  # Import Celery app from the root project

__all__ = ('celery_app',)