from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = "__all__"

    def get_user_info(self, obj):
        return {
            'first_name': obj.user.first_name,
            'last_name': obj.user.last_name,
            'email': obj.user.email
        }

class NotificationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"
