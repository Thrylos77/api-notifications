from rest_framework import serializers
from .models import Notification
from django.contrib.auth import get_user_model

User = get_user_model()

class UserInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']


class NotificationSerializer(serializers.ModelSerializer):
    user_info = UserInfoSerializer(source='user', read_only=True)
    created_at = serializers.DateTimeField(format="%d-%m-%Y %H:%M:%S", read_only=True)
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        exclude = ['user', 'is_archived', 'archived_at']

class NotificationListSerializer(serializers.ModelSerializer):
    user_info = UserInfoSerializer(source='user')
    created_at = serializers.DateTimeField(format="%d-%m-%Y %H:%M:%S", read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'title', 'is_read', 'created_at', 'user_info']


class NotificationLogSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%d-%m-%Y %H:%M:%S", read_only=True)
    class Meta:
        model = Notification
        fields = "__all__"
