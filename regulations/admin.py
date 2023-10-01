from django.contrib import admin

from .models import Regulations


@admin.register(Regulations)
class RegulationsAdmin(admin.ModelAdmin):
    list_display = ["id", "search", "status", "user", "created_at"]
    list_filter = ["status"]
    search_fields = ["search", "user__email"]
