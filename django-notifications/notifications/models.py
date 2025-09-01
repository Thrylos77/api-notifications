from django.db import models
from django.conf import settings

# Create your models here.
class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

class NotificationLog(models.Model):
    notification = models.ForeignKey(
        Notification, 
        on_delete=models.CASCADE,
        related_name='notification_logs'
    )
    channel = models.CharField(max_length=50, choices=[
        ("email", "Email"),
        ("websocket", "WebSocket"),
        ("db", "Database"),
    ])
    status = models.CharField(max_length=50, choices=[
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ], default="pending")
    detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
