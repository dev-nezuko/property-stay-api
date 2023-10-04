from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

CustomUser = get_user_model()


class UserCreationTests(APITestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_superuser(
            email="admin@example.com",
            password="AdminPass!123",
        )

    def test_admin_creates_user_with_secure_temporary_password(self):
        """
        Ensure that when an admin creates a user via the API, the user is
        marked as first login and does not store the raw password value.
        """
        self.client.force_authenticate(user=self.admin)
        url = reverse("user-list-create")
        payload = {
            "email": "newuser@example.com",
            "first_name": "New",
            "last_name": "User",
            "user_type": "client",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_user = CustomUser.objects.get(email="newuser@example.com")
        self.assertTrue(created_user.is_first_login)
        self.assertTrue(created_user.is_active)
        # The password field on the model must be a hashed value and not empty.
        self.assertNotEqual(created_user.password, "")
        self.assertNotIn("password", response.data)


class FirstTimePasswordUpdateTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="user@example.com",
            password="TempPass!123",
            is_first_login=True,
        )
        self.other_user = CustomUser.objects.create_user(
            email="other@example.com",
            password="OtherPass!123",
            is_first_login=True,
        )

    def test_user_can_update_own_password_on_first_login(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("update-password", kwargs={"pk": self.user.pk})
        payload = {
            "new_password": "NewSecurePass!123",
            "confirm_password": "NewSecurePass!123",
        }

        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_first_login)
        self.assertTrue(self.user.check_password("NewSecurePass!123"))

    def test_user_cannot_update_other_users_password(self):
        self.client.force_authenticate(user=self.other_user)
        url = reverse("update-password", kwargs={"pk": self.user.pk})
        payload = {
            "new_password": "NewSecurePass!123",
            "confirm_password": "NewSecurePass!123",
        }

        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
