# account/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from .forms import EmailAuthenticationForm
from .views import (
    UserListCreateView,
    UserDetailView,
    FirstTimePasswordUpdateView,
    password_change,
    password_reset,
    dashboard,
    LoginView, 
    LogoutView,
    user_profile,
    ClientListCreateView,
    ClientDetailView,
    CustomerListView,
    CustomerCreateView,
    CustomerDetailView,
)

urlpatterns = [
    path('users/', UserListCreateView.as_view(), name='user-list-create'),  # For admin to view and create users
    path('users/<int:pk>/', UserDetailView.as_view(), name='user-detail'),  # For admin to update and delete users
    path('users/update-password/<int:pk>/', FirstTimePasswordUpdateView.as_view(), name='update-password'),  # For first-time password updates
    
    path('clients/', ClientListCreateView.as_view(), name='client-list-create'),  # List and create clients
    path('clients/<int:pk>/', ClientDetailView.as_view(), name='client-detail'),  # Get, update, delete a client
    path('clients/<int:client_id>/customers/', CustomerListView.as_view(), name='customer-list'),  # List customers for a specific client
    path('customers/', CustomerListView.as_view(), name='all-customer-list'),  # List all customers for admin
    path('clients/<int:client_id>/customers/create/', CustomerCreateView.as_view(), name='customer-create'),  # Create a customer linked to a client
    path('clients/<int:client_id>/customers/<int:pk>/', CustomerDetailView.as_view(), name='customer-detail'),  # Get, update, delete a customer

    path('password/change/', password_change, name='password-change'),  # Endpoint for changing the password
    path('password/reset/', password_reset, name='password-reset'),  # Endpoint for requesting password reset
    path('dashboard/', dashboard, name='dashboard'),  # User dashboard
    path('login/', auth_views.LoginView.as_view(authentication_form=EmailAuthenticationForm), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),  # User logout
    path('profile/', user_profile, name='user-profile'),  # User profile information
]
