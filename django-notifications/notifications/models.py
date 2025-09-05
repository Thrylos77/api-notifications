# notifications/models.py
"""
Notification core models.

- Notification: the canonical message to deliver (title, message, meta).
- NotificationTarget: raw targets provided at creation time (namespace + type + identifier).
- NotificationDelivery: one DB row per resolved recipient (status, attempts, email/channel).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords


class Notification(models.Model):
    """
    A notification record that represents a message to be delivered.
    The optional `user` FK is kept for backwards-compatibility (author or legacy single-recipient).
    `meta` can store arbitrary JSON metadata (e.g. severity, tags, origin).
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.CASCADE, related_name='notifications'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    """
    Use meta to store arbitrary JSON metadata about the notification.
    Examples:
        - {"severity": "critical"}
        - {"tags": ["system", "maintenance"]}
        - {"origin": "system_xyz"}
    """
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords() # keep a history of changes (optional, useful for audits)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        return f"Notification #{self.pk} - {self.title}"


class NotificationTarget(models.Model):
    """
    Raw declared target for a Notification.
    Examples:
      - namespace='rbac', target_type='group', identifier='5'
      - namespace='default', target_type='email', identifier='foo@example.com'

    The namespace is the resolver key used by the resolver registry to expand this target.
    """
    TARGET_TYPE_USER = "user"
    TARGET_TYPE_GROUP = "group"
    TARGET_TYPE_EMAIL = "email"
    TARGET_TYPE_EXTERNAL = "external"

    TARGET_TYPE_CHOICES = [
        (TARGET_TYPE_USER, "User"),
        (TARGET_TYPE_GROUP, "Group"),
        (TARGET_TYPE_EMAIL, "Email"),
        (TARGET_TYPE_EXTERNAL, "External"),
    ]

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='targets')
    namespace = models.CharField(max_length=100, default='default')  # resolver namespace
    target_type = models.CharField(max_length=20, choices=TARGET_TYPE_CHOICES)
    identifier = models.CharField(max_length=255)  # raw identifier (user id, group id, email, external id)
    """
    Use meta to store per-target metadata that might be useful for resolvers.
    Examples:
        - {"role": "admin"} for a group target to indicate which role to filter
        - {"preferred_channel": "sms"} to indicate preferred delivery channel
    """
    meta = models.JSONField(default=dict, blank=True)  # per-target metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['namespace', 'target_type', 'identifier']),]
        verbose_name = 'Notification Target'
        verbose_name_plural = 'Notification Targets'

    def __str__(self):
        return f"{self.namespace}:{self.target_type}:{self.identifier}"


class NotificationDelivery(models.Model):
    """
    A delivery row represents a single recipient of a Notification after resolution.
    The unique constraint guarantees we don't create duplicate deliveries for the same
    (notification, recipient_namespace, recipient_identifier).
    """
    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='deliveries')
    # link back to the original target (optional - helps traceability)
    target = models.ForeignKey(
        NotificationTarget, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='deliveries'
    )

    # Resolved recipient identity (namespace indicates which resolver/realm)
    recipient_namespace = models.CharField(max_length=100)
    recipient_identifier = models.CharField(max_length=255)  # e.g. "12" or "external:abc"

    # Delivery-specific contact/channel hints (optional)
    recipient_email = models.EmailField(null=True, blank=True)
    recipient_channel = models.CharField(max_length=255, null=True, blank=True)  # e.g. channels group name

    # Delivery state
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    is_read = models.BooleanField(default=False)
    attempts = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)

    # timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['notification', 'recipient_namespace', 'recipient_identifier'],
                name='unique_notification_recipient'
            )
        ]
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['recipient_namespace', 'recipient_identifier']),
        ]
        ordering = ['-created_at']
        verbose_name = 'Notification Delivery'
        verbose_name_plural = 'Notification Deliveries'

    def __str__(self):
        return f"Delivery #{self.pk} -> {self.recipient_namespace}:{self.recipient_identifier} ({self.status})"

    # ------------------------------------------------------------
    # Helper methods to update status safely and record attempt metadata
    # ------------------------------------------------------------
    def mark_attempt(self):
        """
        Increment attempt counter and update last_attempt_at without changing status.
        Use this to record an attempt before actual send.
        """
        self.attempts = (self.attempts or 0) + 1
        self.last_attempt_at = timezone.now()
        # update only the fields we changed to minimize writes
        self.save(update_fields=['attempts', 'last_attempt_at'])

    def mark_sent(self):
        """
        Mark this delivery as sent and record delivered_at.
        This should be called when all required channels (email/WS) were successfully delivered.
        """
        self.status = self.STATUS_SENT
        self.delivered_at = timezone.now()
        self.attempts = (self.attempts or 0) + 1
        self.last_attempt_at = timezone.now()
        self.save(update_fields=['status', 'delivered_at', 'attempts', 'last_attempt_at'])

    def mark_failed(self, error_text=None):
        """
        Mark delivery as failed and persist a truncated error message.
        """
        self.status = self.STATUS_FAILED
        self.error = (error_text or '')[:2000]  # avoid giant error fields
        self.attempts = (self.attempts or 0) + 1
        self.last_attempt_at = timezone.now()
        self.save(update_fields=['status', 'error', 'attempts', 'last_attempt_at'])
