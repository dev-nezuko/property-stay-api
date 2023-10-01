from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RegulationsViewSet

# Create a router and register our viewset with it
router = DefaultRouter()
router.register(r'regulations', RegulationsViewSet, basename='regulations')


urlpatterns = [
    path('', include(router.urls)),
]

