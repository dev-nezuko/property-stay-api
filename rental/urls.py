# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/rental/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rental.views import RentalPropertyViewSet

router = DefaultRouter()
router.register(r'rental_properties', RentalPropertyViewSet, basename='rental-properties')


urlpatterns = [
    path('', include(router.urls)),
]
