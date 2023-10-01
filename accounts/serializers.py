# bnbu_backend_api/account/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

# Get the CustomUser model
CustomUser = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the CustomUser model.
    Used for retrieving, creating, and updating user information.
    """
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'user_type', 'is_active', 'is_first_login']
        read_only_fields = ['id', 'is_active', 'is_first_login']  # These fields cannot be updated via the serializer

    def create(self, validated_data):
        """Create a new user with a temporary password and mark as first login."""
        password = 'temporary_password123'  # Set a temporary password
        user = CustomUser(**validated_data)
        user.set_password(password)  # Set password to the user
        user.is_first_login = True  # Mark as first login
        user.save()
        return user

    def update(self, instance, validated_data):
        """Update user information and optionally change the password."""
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)  # Update password if provided
        instance.is_first_login = False  # Reset after password change
        instance.save()
        return instance

# class ClientSerializer(UserSerializer):
#     class Meta(UserSerializer.Meta):
#         fields = ['id', 'email', 'user_type']  # Limit fields for clients

class CustomerSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'user_type', 'is_active', 'is_first_login', 'client']  # Include client field for customers


class PasswordChangeSerializer(serializers.Serializer):
    """
    Serializer for password change.
    """
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_new_password = serializers.CharField(required=True, write_only=True)

    def validate_new_password(self, value):
        """Validate the new password against Django's password validation."""
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value

    def validate(self, data):
        """Check that the old password is correct and new passwords match."""
        user = self.context['request'].user
        if not user.check_password(data['old_password']):
            raise serializers.ValidationError({"old_password": "Old password is incorrect."})

        if data['new_password'] != data['confirm_new_password']:
            raise serializers.ValidationError({"confirm_new_password": "New password and confirm password do not match."})

        return data
    
    def save(self, **kwargs):
        """Set the new password for the user."""
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user

class PasswordResetSerializer(serializers.Serializer):
    """
    Serializer for password reset requests.
    """
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        """Validate the email for existing users."""
        if not CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email does not exist.")
        return value


class FirstTimePasswordUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating the password on first login.
    """
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = ['new_password', 'confirm_password']

    def validate(self, data):
        """Ensure the new password and confirmation match."""
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        if new_password != confirm_password:
            raise serializers.ValidationError("Passwords do not match.")
        
        # Additional validations for password complexity can be added here
        return data

    def save(self, **kwargs):
        """Set the new password and mark as no longer first login."""
        user = self.instance
        user.set_password(self.validated_data['new_password'])
        user.is_first_login = False  # Mark user as not first login
        user.save()
        return user

    

