from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class RegistrationSerializer(serializers.ModelSerializer):
    """Resident self-registration. Role is fixed to the default (resident).
    Elevating to faculty/admin is an admin action via the Django admin."""

    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ("id", "email", "password", "first_name", "last_name")
        read_only_fields = ("id",)

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "role", "is_staff")
        read_only_fields = fields
