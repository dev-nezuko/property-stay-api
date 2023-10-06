from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from .models import RentalProperty
from unittest.mock import patch
class RentalIsolationTests(APITestCase):
    def setUp(self):
        User=get_user_model();self.owner=User.objects.create_user(email='rental-owner@example.test',password='Synthetic!456',user_type='client');self.other=User.objects.create_user(email='rental-other@example.test',password='Synthetic!456',user_type='client')
        self.row=RentalProperty.objects.create(user_id=self.owner.pk,location='Synthetic place',batch_id=1,property_zillow_link='https://example.invalid/property')
        self.client.force_authenticate(self.other)
    def test_list_and_all_properties_exclude_other_owner(self):
        for path in ['/api/rental_properties/','/api/rental_properties/all-properties/']:
            response=self.client.get(path);self.assertEqual(response.status_code,200);self.assertNotIn('Synthetic place',str(response.data))
    def test_unowned_task_cannot_access_broker_result(self):
        with patch('rental.views.AsyncResult') as result:
            response=self.client.get('/api/rental_properties/task-result/',{'task_id':'synthetic-unowned'})
        self.assertEqual(response.status_code,403);result.assert_not_called()
    def test_owner_is_readonly_during_update(self):
        self.client.force_authenticate(self.owner)
        response=self.client.patch(f'/api/rental_properties/{self.row.pk}/',{'user_id':self.other.pk},format='json')
        self.assertEqual(response.status_code,200);self.row.refresh_from_db();self.assertEqual(self.row.user_id,self.owner.pk)
