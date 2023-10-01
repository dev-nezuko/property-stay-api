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


class CustomerAccessControlTests(APITestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_superuser(
            email="admin2@example.com",
            password="AdminPass!123",
        )
        self.client_user = CustomUser.objects.create_user(
            email="client@example.com",
            password="ClientPass!123",
            user_type="client",
            is_first_login=False,
        )
        self.other_client_user = CustomUser.objects.create_user(
            email="other-client@example.com",
            password="ClientPass!123",
            user_type="client",
            is_first_login=False,
        )
        self.customer = CustomUser.objects.create_user(
            email="customer@example.com",
            password="CustomerPass!123",
            user_type="customer",
            client=self.client_user,
            is_first_login=False,
        )

    def test_admin_can_access_any_customer(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse(
            "customer-detail",
            kwargs={"client_id": self.client_user.pk, "pk": self.customer.pk},
        )

        response = self.client.get(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.customer.email)

    def test_client_cannot_access_customer_of_another_client(self):
        self.client.force_authenticate(user=self.other_client_user)
        url = reverse(
            "customer-detail",
            kwargs={"client_id": self.client_user.pk, "pk": self.customer.pk},
        )

        response = self.client.get(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SecurityRegressionTests(APITestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create_user(
            email="owner@example.test", password="SyntheticPass!456", user_type="client"
        )
        self.other = CustomUser.objects.create_user(
            email="other@example.test", password="SyntheticPass!789", user_type="client"
        )
        self.client.force_authenticate(self.other)

    def test_first_login_patch_and_put_cannot_bypass_owner_check(self):
        url = reverse("update-password", kwargs={"pk": self.owner.pk})
        for method in [self.client.patch, self.client.put]:
            payload = {"new_password": "Replacement!456", "confirm_password": "Replacement!456"}
            self.assertEqual(method(url, payload, format="json").status_code, 405)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password("SyntheticPass!456"))

    def test_password_reset_never_returns_a_token_or_enumerates_accounts(self):
        self.client.force_authenticate(None)
        a = self.client.post(reverse("password-reset"), {"email": self.owner.email}, format="json")
        b = self.client.post(reverse("password-reset"), {"email": "missing@example.test"}, format="json")
        self.assertEqual(a.status_code, 503)
        self.assertEqual(a.data, b.data)
        self.assertNotIn("reset_link", a.data)

    def test_customer_creation_cannot_promote_or_choose_another_owner(self):
        url = reverse("customer-create", kwargs={"client_id": self.other.pk})
        response = self.client.post(
            url, {"email": "new@example.test", "user_type": "admin", "client": self.owner.pk}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        created = CustomUser.objects.get(email="new@example.test")
        self.assertEqual(created.user_type, "customer")
        self.assertEqual(created.client, self.other)

    def test_customer_cannot_create_customers(self):
        customer = CustomUser.objects.create_user(
            email="customer3@example.test", password="SyntheticPass!456", user_type="customer", client=self.other
        )
        self.client.force_authenticate(customer)
        response = self.client.post(
            reverse("customer-create", kwargs={"client_id": self.other.pk}), {"email": "blocked@example.test"},
            format="json"
        )
        self.assertEqual(response.status_code, 403)


class CustomerListScopeTests(APITestCase):
    def setUp(self):
        self.client_a = CustomUser.objects.create_user(email="a@example.test", password="Synthetic!456",
                                                       user_type="client")
        self.client_b = CustomUser.objects.create_user(email="b@example.test", password="Synthetic!456",
                                                       user_type="client")
        CustomUser.objects.create_user(email="cust-b@example.test", password="Synthetic!456",
                                       user_type="customer", client=self.client_b)

    def test_client_cannot_list_another_clients_customers(self):
        self.client.force_authenticate(self.client_a)
        response = self.client.get(reverse("customer-list", kwargs={"client_id": self.client_b.pk}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_lists_own_customers(self):
        self.client.force_authenticate(self.client_b)
        response = self.client.get(reverse("customer-list", kwargs={"client_id": self.client_b.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["email"] for row in response.data], ["cust-b@example.test"])


class FirstLoginFlagTests(APITestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_superuser(email="flag-admin@example.test", password="Synthetic!456")
        self.client_user = CustomUser.objects.create_user(email="flag-client@example.test", password="Synthetic!456",
                                                          user_type="client", is_first_login=False)
        self.customer = CustomUser.objects.create_user(email="flag-customer@example.test",
                                                       password="Synthetic!456", user_type="customer",
                                                       client=self.client_user)

    def test_admin_profile_edit_keeps_first_login_requirement(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(reverse("user-detail", kwargs={"pk": self.customer.pk}),
                                     {"first_name": "Renamed"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, "Renamed")
        self.assertTrue(self.customer.is_first_login)

    def test_client_customer_edit_keeps_first_login_requirement(self):
        self.client.force_authenticate(self.client_user)
        url = reverse("customer-detail", kwargs={"client_id": self.client_user.pk, "pk": self.customer.pk})
        response = self.client.put(url, {"email": self.customer.email, "last_name": "Edited"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_first_login)


class TokenLoginTests(APITestCase):
    def test_email_login_issues_tokens_and_inactive_accounts_are_refused(self):
        CustomUser.objects.create_user(email="active@example.test", password="Synthetic!456")
        CustomUser.objects.create_user(email="inactive@example.test", password="Synthetic!456", is_active=False)
        ok = self.client.post(reverse("token_obtain_pair"),
                              {"email": "active@example.test", "password": "Synthetic!456"}, format="json")
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertIn("access", ok.data)
        refused = self.client.post(reverse("token_obtain_pair"),
                                   {"email": "inactive@example.test", "password": "Synthetic!456"}, format="json")
        self.assertEqual(refused.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_template_login_route_without_a_template_is_gone(self):
        self.assertEqual(self.client.get("/account/login/").status_code, status.HTTP_404_NOT_FOUND)
