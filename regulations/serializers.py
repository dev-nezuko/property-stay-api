from rest_framework import serializers
from .models import Regulations

class RegulationsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Regulations
        fields = ['id', 'date', 'search', 'status', 'gpt_response', 'chat_history']
        read_only_fields = ['gpt_response', 'chat_history']

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
        required=False,
        help_text="Optional; must match the regulation in the URL."
    )

