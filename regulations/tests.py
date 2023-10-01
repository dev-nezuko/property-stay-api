from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from .models import Regulations
from unittest.mock import patch
class RegulationIsolationTests(APITestCase):
    def setUp(self):
        User=get_user_model();self.owner=User.objects.create_user(email='reg-owner@example.test',password='Synthetic!456',user_type='client');self.other=User.objects.create_user(email='reg-other@example.test',password='Synthetic!456',user_type='client')
        self.row=Regulations.objects.create(user=self.owner,search='Synthetic location')
        self.client.force_authenticate(self.other)
    def test_search_excludes_another_owner(self):
        response=self.client.get('/api/regulations/search/')
        self.assertEqual(response.status_code,200);self.assertNotIn('Synthetic location',str(response.data))
    def test_history_cannot_read_another_owners_analysis(self):
        self.assertEqual(self.client.get(f'/api/regulations/{self.row.pk}/get-chat-history/').status_code,404)
