from __future__ import absolute_import, unicode_literals
import logging
from celery import shared_task
from .utils import analyze_document_with_gpt
from .models import Document
logger = logging.getLogger(__name__)


@shared_task
def analyze_document_task(document_id):
    logger.info("Starting analyze_document_task for document ID: %s.", document_id)
    document = Document.objects.filter(pk=document_id).first()
    if document is None:
        logger.warning("Document %s no longer exists; skipping analysis.", document_id)
        return
    response = analyze_document_with_gpt(document)
    document.gpt_response = response
    # A failed analysis keeps the review status, so the lease never inherits "Error".
    if response["status"] != "Error":
        document.status = response["status"]
    document.save()
    logger.info("Document %s analysis saved with status %s.", document_id, response["status"])
