from rest_framework.exceptions import ValidationError
from rest_framework import serializers
from .models import Regulations

class RegulationsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Regulations
        fields = ['id', 'date', 'search', 'status', 'gpt_response', 'chat_history']

    # Explicitly mark address and area as optional
    # address = serializers.CharField(required=False, allow_blank=True)
    # area = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        # Ensure the 'city' field is provided
        if not data.get('search'):
            raise ValidationError('The city field is required.')

        # Ensure at least one of address or area is provided
        # if not data.get('address') and not data.get('area'):
        #     raise ValidationError('At least one of address or area must be provided.')

        return data

    def create(self, validated_data):
        # Get user from request context
        user = self.context['request'].user
        validated_data['user'] = user

        return Regulations.objects.create(**validated_data)
    
class GPTChatSerializer(serializers.Serializer):
    message = serializers.CharField(
        required=True,
        allow_blank=False,
        help_text="Enter your message or prompt to interact with the GPT model."
    )
    regulation_id = serializers.IntegerField(
        required=True,
        help_text="Enter the ID of the regulation to interact with."
    )

