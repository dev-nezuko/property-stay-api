import csv
import io

from django.utils import timezone
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


class RentalFilterAndExportTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(email='filter-owner@example.test', password='Synthetic!456',
                                              user_type='client')
        self.other = User.objects.create_user(email='filter-other@example.test', password='Synthetic!456',
                                              user_type='client')
        RentalProperty.objects.create(user_id=self.owner.pk, location='12 Demo St, Example', batch_id=3,
                                      monthly_estimated_profit=1800, property_status='Approved',
                                      property_zillow_link='https://example.invalid/a')
        RentalProperty.objects.create(user_id=self.owner.pk, location=None, batch_id=4,
                                      monthly_estimated_profit=200, property_status='Rejected',
                                      property_zillow_link='https://example.invalid/b')
        RentalProperty.objects.create(user_id=self.other.pk, location='=HYPERLINK("x")', batch_id=5,
                                      property_zillow_link='https://example.invalid/c')
        self.client.force_authenticate(self.owner)

    def test_invalid_dates_return_400_instead_of_crashing(self):
        response = self.client.post('/api/rental_properties/filtered-list/',
                                    {'status': 'Approved', 'start_date': '2024-12-03'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('start_date', response.data)
        response = self.client.get('/api/rental_properties/download-csv/', {'status': 'Approved', 'end_date': 'nope'})
        self.assertEqual(response.status_code, 400)

    def test_invalid_profit_returns_400(self):
        response = self.client.post('/api/rental_properties/filtered-list/', {'min_profit': 'lots'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_filtered_list_applies_filters_within_owner_scope(self):
        response = self.client.post('/api/rental_properties/filtered-list/', {'min_profit': 1000}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']['all_batch_ids'], [3])

    def test_end_date_includes_the_whole_day(self):
        today = timezone.now().strftime('%B %d, %Y')
        response = self.client.post('/api/rental_properties/filtered-list/',
                                    {'start_date': today, 'end_date': today}, format='json')
        self.assertEqual(response.data['count'], 2)

    def test_csv_export_handles_missing_location_and_scopes_rows(self):
        response = self.client.get('/api/rental_properties/download-csv/')
        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(b''.join(response.streaming_content).decode())))
        self.assertEqual(rows[0][0], 'Date')
        self.assertEqual(len(rows), 3)
        self.assertIn('12 Demo St, Example', [row[2] for row in rows])

    def test_csv_export_neutralises_formula_cells(self):
        self.client.force_authenticate(self.other)
        response = self.client.get('/api/rental_properties/download-csv/')
        rows = list(csv.reader(io.StringIO(b''.join(response.streaming_content).decode())))
        self.assertEqual(rows[1][2], '\'=HYPERLINK("x")')
