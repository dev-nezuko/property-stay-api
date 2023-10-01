# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/lease/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LeaseViewSet, DocumentViewSet

# Create a router and register our viewset with it
router = DefaultRouter()
router.register(r'leases', LeaseViewSet, basename='lease')
router.register(r'documents', DocumentViewSet, basename='document')

urlpatterns = [
    path('', include(router.urls)),  # Include the router URLs
]
