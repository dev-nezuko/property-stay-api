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


class RegulationChatTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(email='chat-owner@example.test', password='Synthetic!456',
                                              user_type='client')
        self.other = User.objects.create_user(email='chat-other@example.test', password='Synthetic!456',
                                              user_type='client')
        self.mine = Regulations.objects.create(user=self.owner, search='Demo town',
                                               chat_history=[{'role': 'user', 'content': 'Hi', 'timestamp': 't'}])
        self.theirs = Regulations.objects.create(user=self.other, search='Other town')
        self.client.force_authenticate(self.owner)

    def test_chat_sends_messages_without_timestamps(self):
        completion = {'choices': [{'message': {'content': 'Permits are required.'}}]}
        with patch('regulations.views.openai.ChatCompletion.create', return_value=completion) as create:
            response = self.client.post(f'/api/regulations/{self.mine.pk}/chat/', {'message': 'Permit?'},
                                        format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(set(m) == {'role', 'content'} for m in create.call_args.kwargs['messages']))

    def test_chat_cannot_target_another_owners_regulation(self):
        with patch('regulations.views.openai.ChatCompletion.create') as create:
            response = self.client.post(f'/api/regulations/{self.theirs.pk}/chat/', {'message': 'Hi'}, format='json')
        self.assertEqual(response.status_code, 404)
        create.assert_not_called()

    def test_chat_rejects_mismatched_body_id(self):
        response = self.client.post(f'/api/regulations/{self.mine.pk}/chat/',
                                    {'message': 'Hi', 'regulation_id': self.theirs.pk}, format='json')
        self.assertEqual(response.status_code, 400)


class RegulationWriteProtectionTests(APITestCase):
    def test_owner_cannot_forge_model_output(self):
        owner = get_user_model().objects.create_user(email='forge@example.test', password='Synthetic!456',
                                                     user_type='client')
        row = Regulations.objects.create(user=owner, search='Demo city')
        self.client.force_authenticate(owner)
        response = self.client.patch(f'/api/regulations/{row.pk}/',
                                     {'gpt_response': {'message': 'forged'}, 'chat_history': [{'role': 'x'}]},
                                     format='json')
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertIsNone(row.gpt_response)
        self.assertEqual(row.chat_history, [])

    def test_create_still_requires_a_search(self):
        owner = get_user_model().objects.create_user(email='blank@example.test', password='Synthetic!456',
                                                     user_type='client')
        self.client.force_authenticate(owner)
        response = self.client.post('/api/regulations/', {'search': ''}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('search', response.data)
