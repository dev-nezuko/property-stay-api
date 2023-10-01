# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/rental/serializers.py
from rest_framework import serializers
from rental.models import RentalProperty


class RentalPropertySerializer(serializers.ModelSerializer):
    created_at_formatted = serializers.SerializerMethodField()

    class Meta:
        model = RentalProperty
        fields = "__all__"
        extra_fields = ['created_at_formatted']  # Include additional formatted field

    def get_created_at_formatted(self, obj):
        if obj.created_at:
            return obj.created_at.strftime('%B %d, %Y')  # Format as "December 3, 2024"
        return None
