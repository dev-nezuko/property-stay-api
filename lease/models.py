# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/lease/models.py
from django.db import models
from django.conf import settings


class Lease(models.Model):
    STATUS_CHOICES = [
        ("Draft", "Draft"),
        ("Rejected", "Rejected"),
        ("Approved", "Approved"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="leases"
    )
    date = models.DateField(auto_now_add=True)
    address1 = models.CharField(max_length=255)
    address2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    zip_code = models.CharField(max_length=10)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Draft")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def num_of_docs(self):
        return self.documents.count()

    @property
    def address(self):
        return f"{self.address1}{', ' + self.address2 if self.address2 else ''}"

    def __str__(self):
        return f"{self.address} - {self.city} - {self.status}"


class Document(models.Model):
    STATUS_CHOICES = [
        ("Draft", "Draft"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
        ("Pending", "Pending"),
    ]
    lease = models.ForeignKey(Lease, related_name="documents", on_delete=models.CASCADE)
    file = models.FileField(upload_to="documents/", blank=True, null=True)
    file_url = models.URLField(blank=True, null=True)
    name = models.CharField(max_length=255)
    version = models.PositiveIntegerField(default=1)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")
    gpt_response = models.JSONField(blank=True, null=True)
    chat_history = models.JSONField(default=list, blank=True, null=True)

    def save(self, *args, **kwargs):
        # Set the version number to the next version if it's a new document for the lease
        if not self.pk:
            last_document = (
                Document.objects.filter(lease=self.lease).order_by("-version").first()
            )
            self.version = (last_document.version + 1) if last_document else 1
        super().save(*args, **kwargs)

        # Update the lease status to match the latest document's status
        latest_document = (
            Document.objects.filter(lease=self.lease).order_by("-version").first()
        )
        if latest_document and latest_document.status != self.lease.status:
            self.lease.status = latest_document.status
            self.lease.save()

    def __str__(self):
        return f"Document for Lease {self.lease.id} - {self.name} (Version {self.version}) - {self.status}"
