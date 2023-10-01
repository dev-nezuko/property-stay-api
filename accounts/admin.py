from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ["id", "email", "user_type", "is_staff", "is_active"]
    list_filter = ["user_type", "is_staff", "is_active"]

    # Remove username from fieldsets and add email
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("user_type", "is_first_login")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    # Remove username from add_fieldsets and add email
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "user_type"),
            },
        ),
    )

    ordering = ["email"]
    search_fields = ["email"]


admin.site.register(CustomUser, CustomUserAdmin)
