from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from unittest.mock import patch
from .models import Lease,Document
class OwnerIsolationTests(APITestCase):
    def setUp(self):
        User=get_user_model()
        self.owner=User.objects.create_user(email="lease-owner@example.test",password="Synthetic!456",user_type="client")
        self.other=User.objects.create_user(email="lease-other@example.test",password="Synthetic!456",user_type="client")
        self.lease=Lease.objects.create(user=self.owner,address1="Synthetic address",city="Example",state="WA",zip_code="00000")
        self.document=Document.objects.create(lease=self.lease,name="synthetic.pdf",file_url="https://example.invalid/synthetic.pdf")
        self.client.force_authenticate(self.other)
    def test_lease_search_excludes_another_owner(self):
        response=self.client.get('/api/leases/search/')
        self.assertEqual(response.status_code,200);self.assertEqual(response.data['count'],0)
    def test_documents_list_and_history_exclude_another_owner(self):
        response=self.client.get('/api/documents/')
        self.assertEqual(response.status_code,200);self.assertEqual(response.data['count'],0)
        self.assertEqual(self.client.get(f'/api/documents/{self.document.pk}/get-chat-history/').status_code,404)
    def test_review_cannot_queue_another_owners_document(self):
        with patch('lease.views.analyze_document_task.delay') as enqueue:
            response=self.client.post('/api/documents/review/',{'document_ids':[self.document.pk]},format='json')
        self.assertEqual(response.status_code,404);enqueue.assert_not_called()
    def test_owner_can_read_own_history(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(f'/api/documents/{self.document.pk}/get-chat-history/').status_code,200)

    def test_document_upload_is_disabled_before_storage_calls(self):
        from .serializers import LeaseUploadSerializer
        from rest_framework.exceptions import ValidationError
        from django.core.files.uploadedfile import SimpleUploadedFile
        with patch('lease.serializers.upload') as upload:
            with self.assertRaises(ValidationError):
                LeaseUploadSerializer().create({'documents':[SimpleUploadedFile('synthetic.txt',b'demo')]})
        upload.assert_not_called()

    def test_preview_cannot_return_another_owners_document_url(self):
        response=self.client.get(f'/api/documents/preview/{self.document.pk}/')
        self.assertEqual(response.status_code,404);self.assertNotIn('example.invalid',str(response.data))
