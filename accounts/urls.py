from django.urls import path
from .views import (
    UserListCreateView,
    UserDetailView,
    FirstTimePasswordUpdateView,
    password_change,
    password_reset,
    dashboard,
    LogoutView,
    user_profile,
    ClientListCreateView,
    ClientDetailView,
    CustomerListView,
    CustomerCreateView,
    CustomerDetailView,
)

urlpatterns = [
    path('users/', UserListCreateView.as_view(), name='user-list-create'),
    path('users/<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    path('users/update-password/<int:pk>/', FirstTimePasswordUpdateView.as_view(), name='update-password'),

    path('clients/', ClientListCreateView.as_view(), name='client-list-create'),
    path('clients/<int:pk>/', ClientDetailView.as_view(), name='client-detail'),
    path('clients/<int:client_id>/customers/', CustomerListView.as_view(), name='customer-list'),
    path('customers/', CustomerListView.as_view(), name='all-customer-list'),
    path('clients/<int:client_id>/customers/create/', CustomerCreateView.as_view(), name='customer-create'),
    path('clients/<int:client_id>/customers/<int:pk>/', CustomerDetailView.as_view(), name='customer-detail'),

    path('password/change/', password_change, name='password-change'),
    path('password/reset/', password_reset, name='password-reset'),
    path('dashboard/', dashboard, name='dashboard'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', user_profile, name='user-profile'),
]
