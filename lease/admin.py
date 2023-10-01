from django.contrib import admin

from .models import Document, Lease


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    list_display = ["id", "address1", "city", "state", "status", "user", "created_at"]
    list_filter = ["status", "state"]
    search_fields = ["address1", "city", "user__email"]


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "lease", "version", "status", "uploaded_at"]
    list_filter = ["status"]
    search_fields = ["name"]
