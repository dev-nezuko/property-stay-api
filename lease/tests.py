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


def _completion(text):
    return {"choices": [{"message": {"content": text}}], "created": 1700000000}


class FakeEncoding:
    """Stands in for tiktoken, which downloads its encoding tables on first use."""

    def encode(self, text):
        return text.split()


class DocumentAnalysisTests(APITestCase):
    def setUp(self):
        encoding = patch("lease.utils.tiktoken.get_encoding", return_value=FakeEncoding())
        encoding.start()
        self.addCleanup(encoding.stop)
        User = get_user_model()
        self.owner = User.objects.create_user(email="analysis-owner@example.test", password="Synthetic!456",
                                              user_type="client")
        self.lease = Lease.objects.create(user=self.owner, address1="1 Demo Way", city="Example", state="WA",
                                          zip_code="00000")
        self.document = Document.objects.create(lease=self.lease, name="demo.pdf",
                                                file_url="https://example.invalid/demo.pdf")

    def test_status_parser_prefers_the_labelled_status(self):
        from .utils import parse_lease_status
        self.assertEqual(parse_lease_status("Status: Rejected\n\nIt was not approved."), "Rejected")
        self.assertEqual(parse_lease_status("Draft terms remain; approval later."), "Draft")
        self.assertEqual(parse_lease_status("Looks fine overall."), "Draft")

    def test_rate_limit_does_not_raise_name_error(self):
        import openai
        from .utils import analyze_chunk
        error = openai.error.RateLimitError("slow down")
        with patch("lease.utils.openai.ChatCompletion.create", side_effect=error), \
                patch("lease.utils.time.sleep") as sleep:
            self.assertIsNone(analyze_chunk("short text", "system"))
        self.assertEqual(sleep.call_count, 2)

    def test_failed_chunk_text_never_reaches_the_final_prompt(self):
        import openai
        from .utils import analyze_document_with_gpt
        calls = []

        def fake_create(**kwargs):
            calls.append(kwargs["messages"][-1]["content"])
            if len(calls) == 1:
                raise openai.error.APIError("provider exploded")
            return _completion("Status: Approved\n\nRent is fair.")

        pages = [type("Page", (), {"extract_text": lambda self, n=n: f"page {n}"})() for n in range(10)]
        reader = type("Reader", (), {"pages": pages})()
        fetched = type("Resp", (), {"status_code": 200, "content": b"%PDF"})()
        with patch("lease.utils.requests.get", return_value=fetched), \
                patch("lease.utils.PyPDF2.PdfReader", return_value=reader), \
                patch("lease.utils.openai.ChatCompletion.create", side_effect=fake_create):
            result = analyze_document_with_gpt(self.document)
        self.assertEqual(result["status"], "Approved")
        self.assertEqual(result["message"], "Rent is fair.")
        self.assertNotIn("provider exploded", calls[-1])

    def test_failed_analysis_keeps_document_and_lease_status(self):
        from .tasks import analyze_document_task
        with patch("lease.tasks.analyze_document_with_gpt",
                   return_value={"status": "Error", "message": "Document analysis failed: offline"}):
            analyze_document_task(self.document.pk)
        self.document.refresh_from_db()
        self.lease.refresh_from_db()
        self.assertEqual(self.document.status, "Pending")
        self.assertEqual(self.document.gpt_response["status"], "Error")
        self.assertNotEqual(self.lease.status, "Error")

    def test_successful_analysis_is_stored_as_json_object(self):
        from .tasks import analyze_document_task
        result = {"status": "Rejected", "message": "High fees.", "created_time": "2024-01-01T00:00:00+00:00"}
        with patch("lease.tasks.analyze_document_with_gpt", return_value=result):
            analyze_document_task(self.document.pk)
        self.document.refresh_from_db()
        self.assertEqual(self.document.gpt_response, result)
        self.assertEqual(self.document.status, "Rejected")

    def test_chat_uses_url_document_and_sends_plain_messages(self):
        self.client.force_authenticate(self.owner)
        self.document.chat_history = [{"role": "user", "content": "Hi", "timestamp": "2024-01-01T00:00:00Z"},
                                      {"role": "assistant", "content": "Hello", "timestamp": "2024-01-01T00:00:01Z"}]
        self.document.save()
        with patch("lease.views.openai.ChatCompletion.create", return_value=_completion("Answer")) as create:
            response = self.client.post(f"/api/documents/{self.document.pk}/chat/", {"message": "Deposit?"},
                                        format="json")
        self.assertEqual(response.status_code, 200)
        messages = create.call_args.kwargs["messages"]
        self.assertTrue(all(set(m) == {"role", "content"} for m in messages))
        self.assertEqual(messages[-1]["content"], "Deposit?")
        self.document.refresh_from_db()
        self.assertEqual(len(self.document.chat_history), 4)

    def test_chat_rejects_mismatched_body_id(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(f"/api/documents/{self.document.pk}/chat/",
                                    {"message": "Hi", "document_id": self.document.pk + 1}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_chat_provider_failure_returns_502_without_details(self):
        import openai
        self.client.force_authenticate(self.owner)
        with patch("lease.views.openai.ChatCompletion.create", side_effect=openai.error.APIError("secret detail")):
            response = self.client.post(f"/api/documents/{self.document.pk}/chat/", {"message": "Hi"},
                                        format="json")
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret detail", str(response.data))
