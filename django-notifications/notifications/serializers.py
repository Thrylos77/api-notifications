# notifications/serializers.py
from django.contrib.auth import get_user_model
from rest_framework import serializers
from django.db import transaction

from .models import Notification, NotificationTarget, NotificationDelivery
from .tasks import process_notification_targets_task

User = get_user_model()


class UserInfoSerializer(serializers.ModelSerializer):
    """Serialize basic user info for display in notifications."""
    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "email"]


class NotificationTargetSerializer(serializers.ModelSerializer):
    """Serializer for NotificationTarget input/output."""
    class Meta:
        model = NotificationTarget
        fields = ("id", "namespace", "target_type", "identifier", "meta", "created_at")
        read_only_fields = ("id", "created_at")


class NotificationDeliverySerializer(serializers.ModelSerializer):
    """Serializer for NotificationDelivery - what is actually delivered to recipients."""
    # include small notification summary
    notification_title = serializers.CharField(source="notification.title", read_only=True)
    notification_message = serializers.CharField(source="notification.message", read_only=True)

    class Meta:
        model = NotificationDelivery
        fields = (
            "id", "notification", "notification_title", "notification_message",
            "target", "recipient_namespace", "recipient_identifier", "recipient_email",
            "recipient_channel", "status", "is_read", "attempts", "last_attempt_at", "error",
            "created_at", "delivered_at",
        )
        read_only_fields = (
            "id", "notification", "notification_title", "notification_message",
            "target", "status", "is_read", "attempts", "last_attempt_at",
            "error", "created_at", "delivered_at",
        )


class NotificationCreateSerializer(serializers.ModelSerializer):
    """
    Serializer used to create a Notification along with its raw targets.
    - Accepts a `targets` list (write-only).
    - Schedules background expansion (resolver -> deliveries) after DB commit.
    """
    targets = NotificationTargetSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = Notification
        fields = ("id", "title", "message", "meta", "user", "targets")
        read_only_fields = ("id",)

    def create(self, validated_data):
        # Pop targets list (if any) then create Notification instance
        targets_data = validated_data.pop("targets", [])
        # If user was not provided in payload, we expect the view to set request.user
        notif = Notification.objects.create(**validated_data)

        # Bulk create NotificationTarget rows
        objs = []
        for t in targets_data:
            objs.append(NotificationTarget(
                notification=notif,
                namespace=t.get("namespace", "default"),
                target_type=t["target_type"],
                identifier=str(t["identifier"]),
                meta=t.get("meta", {}),
            ))
        if objs:
            # bulk_create is efficient; ignore_conflicts not available on very old Django versions
            NotificationTarget.objects.bulk_create(objs)

        # Schedule the expansion task after the current DB transaction successfully commits.
        # This avoids the Celery worker seeing an uncommitted notification/targets.
        transaction.on_commit(lambda: process_notification_targets_task.delay(notif.pk))

        return notif


class NotificationDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for Notification detail view.
    - Includes nested targets and a deliveries summary.
    """
    targets = NotificationTargetSerializer(many=True, read_only=True)
    deliveries = NotificationDeliverySerializer(many=True, read_only=True)
    created_at = serializers.DateTimeField(format="%d-%m-%Y %H:%M:%S", read_only=True)

    class Meta:
        model = Notification
        fields = ("id", "title", "message", "meta", "created_at", "targets", "deliveries")


class NotificationListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing Notifications (for admins / creators).
    """
    created_at = serializers.DateTimeField(format="%d-%m-%Y %H:%M:%S", read_only=True)
    deliveries_count = serializers.IntegerField(source="deliveries.count", read_only=True)

    class Meta:
        model = Notification
        fields = ("id", "title", "created_at", "deliveries_count")

class HistoricalNotificationSerializer(serializers.ModelSerializer): 
    history_user = serializers.StringRelatedField()
    history_type_display = serializers.CharField(source='get_history_type_display', read_only=True)

    class Meta:
        model = Notification.history.model
        fields = [ 'history_id', 'history_date', 'history_type_display', 'history_user', 'title', 'message', 'user']