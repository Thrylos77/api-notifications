
"""
Signal handlers to enqueue notification tasks.

Design:
- When a Notification is created (post_save with created=True), enqueue the
  asynchronous task to deliver the email, or send a websocket notification.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Notification
from .serializers import NotificationSerializer
from .tasks import send_notification_email_task


@receiver(post_save, sender=Notification)
def notification_created(sender, instance, created, **kwargs):
    """
    Send a WebSocket notification when a new notification is created.
    """
    if created:
        channel_layer = get_channel_layer()
        group_name = f"notification"
        
        serializer = NotificationSerializer(instance)
        message = serializer.data

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "send_notification",
                "message": message
            }
        )

@receiver(post_save, sender=Notification)
def enqueue_notification_email(sender, instance, created, **kwargs):
    """
    Signal handler that enqueues the email sending Celery task when a Notification
    object is created.

    Notes:
    - Do not perform the send operation synchronously inside the handler:
      signals run in the main request process and must be fast.
    - We pass only the Notification PK to the task to avoid serializing large data.
    """
    if not created:
        return

    # fire-and-forget: send the task to the Celery broker (Redis)
    send_notification_email_task.delay(instance.pk)