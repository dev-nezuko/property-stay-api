import csv
import io

from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from .models import RentalProperty
from unittest.mock import patch


class RentalIsolationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email='rental-owner@example.test', password='Synthetic!456', user_type='client'
        )
        self.other = User.objects.create_user(
            email='rental-other@example.test', password='Synthetic!456', user_type='client'
        )
        self.row = RentalProperty.objects.create(
            user_id=self.owner.pk, location='Synthetic place', batch_id=1,
            property_zillow_link='https://example.invalid/property'
        )
        self.client.force_authenticate(self.other)

    def test_list_and_all_properties_exclude_other_owner(self):
        for path in ['/api/rental_properties/', '/api/rental_properties/all-properties/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('Synthetic place', str(response.data))

    def test_unowned_task_cannot_access_broker_result(self):
        with patch('rental.views.AsyncResult') as result:
            response = self.client.get('/api/rental_properties/task-result/', {'task_id': 'synthetic-unowned'})
        self.assertEqual(response.status_code, 403)
        result.assert_not_called()

    def test_owner_is_readonly_during_update(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            f'/api/rental_properties/{self.row.pk}/', {'user_id': self.other.pk}, format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.row.refresh_from_db()
        self.assertEqual(self.row.user_id, self.owner.pk)


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


SAMPLE_CSV = (
    'Location,Price,Sq. ft.,Ba,Br,Link\n'
    '"10 Demo Ave, Example, FL",$2000/mo,"1,200 sqft",2 ba,2 bds,https://example.invalid/10\n'
    '"11 Demo Ave, Example, FL","$1,500/mo",,1 ba,1 bds,https://example.invalid/11\n'
)


class RentalUploadTests(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.owner = get_user_model().objects.create_user(email='upload@example.test', password='Synthetic!456',
                                                          user_type='client')
        self.client.force_authenticate(self.owner)

    def upload(self, name='listings.csv', body=SAMPLE_CSV):
        from django.core.files.uploadedfile import SimpleUploadedFile
        task = type('Task', (), {'id': f'task-{name}'})()
        with patch('rental.views.process_rental_properties_task.delay', return_value=task) as delay:
            response = self.client.post('/api/rental_properties/upload-properties/',
                                        {'file': SimpleUploadedFile(name, body.encode())}, format='multipart')
        return response, delay

    def test_upload_queues_cleaned_rows_and_records_task_owner(self):
        response, delay = self.upload()
        self.assertEqual(response.status_code, 202)
        rows, context = delay.call_args.args
        self.assertEqual(context, {'user': self.owner.pk, 'new_batch_id': 1})
        self.assertIn('"Price":2000', rows)
        with patch('rental.views.AsyncResult') as result:
            result.return_value.state = 'PENDING'
            progress = self.client.get('/api/rental_properties/task-progress/', {'task_id': response.data['task_id']})
        self.assertEqual(progress.status_code, 202)

    def test_back_to_back_uploads_get_distinct_batches(self):
        RentalProperty.objects.create(user_id=self.owner.pk, batch_id=7, property_zillow_link='https://example.invalid')
        first, _ = self.upload('a.csv')
        second, _ = self.upload('b.CSV')
        self.assertEqual([first.data['message'], second.data['message']],
                         ['Batch 8 processing started', 'Batch 9 processing started'])

    def test_unreadable_or_unsupported_files_are_rejected(self):
        self.assertEqual(self.upload('broken.xlsx', 'not a zip')[0].status_code, 400)
        self.assertEqual(self.upload('legacy.xls')[0].status_code, 400)
        response, _ = self.upload('cols.csv', 'Location,Price\nA,1\n')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Ba, Br, Link, Sq. ft.', response.data['message'])


class RentalTaskTests(APITestCase):
    def airdna_results(self, queries):
        revenue = {'10 Demo Ave, Example, FL': 90000, '12 Demo Ave, Example, FL': 20000}
        return [{'stats': {'future': {'summary': {'adr': 250, 'occupancy': 0.7, 'revenue': revenue[q['address']]}}},
                 'details': {'address': q['address']}} for q in queries]

    def test_task_saves_enriched_rows_and_pushes_approved_ones(self):
        import json
        from .tasks import process_rental_properties_task
        rows = json.dumps([
            {'Location': '10 Demo Ave, Example, FL', 'Price': 2000, 'Sq. ft.': 1200, 'Ba': 2, 'Br': 2,
             'Link': 'https://example.invalid/10'},
            {'Location': '12 Demo Ave, Example, FL', 'Price': 2500, 'Sq. ft.': None, 'Ba': 1, 'Br': 1,
             'Link': 'https://example.invalid/12'},
        ])
        with patch('rental.tasks.process_airdna_api', side_effect=self.airdna_results), \
                patch('rental.tasks.upload_properties_to_clickup') as clickup, \
                patch.object(process_rental_properties_task, 'update_state'):
            process_rental_properties_task(rows, {'user': 42, 'new_batch_id': 5})
        saved = RentalProperty.objects.get()
        self.assertEqual((saved.user_id, saved.batch_id, saved.property_status), (42, 5, 'Approved'))
        # (90000 - (2000 * 12 + 2 * 2000)) / 12
        self.assertEqual(float(saved.monthly_estimated_profit), 5166.67)
        clickup.assert_called_once()

    def test_task_survives_a_provider_outage(self):
        import json
        from .tasks import process_rental_properties_task
        rows = json.dumps([{'Location': 'X', 'Price': 1, 'Sq. ft.': 1, 'Ba': 1, 'Br': 1, 'Link': 'https://e.invalid'}])
        with patch('rental.tasks.process_airdna_api', side_effect=ValueError('down')), \
                patch.object(process_rental_properties_task, 'update_state'):
            self.assertEqual(process_rental_properties_task(rows, {'user': 1, 'new_batch_id': 1}), '[]')
        self.assertFalse(RentalProperty.objects.exists())


class ProviderConfigurationTests(APITestCase):
    def test_unconfigured_airdna_fails_fast_without_requests(self):
        from bnbu_constants.utility import process_airdna_api
        with patch('bnbu_constants.utility.requests.post') as post, self.settings(AIRDNA_URL=''):
            with self.assertRaisesMessage(ValueError, 'AIRDNA_URL is not configured'):
                process_airdna_api([{'address': 'x'}])
        post.assert_not_called()

    def test_unconfigured_clickup_is_skipped(self):
        from .tasks import upload_properties_to_clickup
        with patch('rental.tasks.requests.post') as post, self.settings(CLICKUP_URL=None):
            self.assertIsNone(upload_properties_to_clickup('Demo', 'https://example.invalid', 'Approved'))
        post.assert_not_called()

    def test_airdna_retries_then_gives_up(self):
        import requests
        from bnbu_constants.utility import AIRDNA_ATTEMPTS, process_airdna_api
        with patch('bnbu_constants.utility.requests.post', side_effect=requests.ConnectionError('offline')) as post, \
                self.settings(AIRDNA_URL='https://airdna.example.invalid', AIRDNA_API_KEY='placeholder'):
            with self.assertRaises(ValueError):
                process_airdna_api([{'address': 'x'}])
        self.assertEqual(post.call_count, AIRDNA_ATTEMPTS)
