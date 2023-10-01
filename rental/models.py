# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/rental/models.py
from django.conf import settings
from django.db import models
import bnbu_constants.constants as constants
    
class RentalProperty(models.Model):
    user_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    rent = models.IntegerField(null=True, blank=True)
    no_of_bedrooms = models.IntegerField(null=True, blank=True)
    no_of_bathrooms = models.IntegerField(null=True, blank=True)
    square_feet = models.IntegerField(null=True, blank=True)
    utilities = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    adr = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    occupancy_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    property_zillow_link = models.URLField()
    property_status = models.CharField(max_length=20, choices=constants.RENTAL_PROPERY_STATUS_CHOICES,
                                       default=constants.PENDING)
    yearly_rent_cost_util = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # Will be extracted from AIR DNA API
    yearly_projected_revenue = models.IntegerField(null=True, blank=True)
    monthly_estimated_profit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    batch_id = models.IntegerField()
