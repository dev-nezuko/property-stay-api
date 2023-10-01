# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/regulations/models.py
from django.db import models
from django.conf import settings

class Regulations(models.Model):
    STATUS_CHOICES = [
        ('STR Allowed', 'STR Allowed'),
        ('STR Not Allowed', 'STR Not Allowed'),
        ('STR Allowed with Restrictions', 'STR Allowed with Restrictions'),
        ('STR Pending Approval', 'STR Pending Approval'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='regulations')
    date = models.DateField(auto_now_add=True)
    search = models.CharField(max_length=255)
    # address = models.CharField(max_length=255)
    # city = models.CharField(max_length=255)
    # area = models.CharField(max_length=255)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    gpt_response = models.JSONField(blank=True, null=True) 
    chat_history = models.JSONField(default=list, blank=True, null=True) 
