# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/lease/tasks.py
from __future__ import absolute_import, unicode_literals
import logging
from celery import shared_task
from .utils import analyze_document_with_gpt
from .models import Document
logger = logging.getLogger(__name__)



@shared_task
def analyze_document_task(document_id):
    logger.info(f"Starting analyze_document_task for document ID: {document_id}.")
    try:
        document = Document.objects.get(pk=document_id)
        response = analyze_document_with_gpt(document)
        document.status = response["status"]
        document.gpt_response = response
        document.save()
        logger.info("Document analysis completed and saved successfully.")
    except Exception as e:
        logger.exception(f"An error occurred in analyze_document_task for document ID: {document_id}.")
  