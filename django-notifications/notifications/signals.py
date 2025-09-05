# notifications/signals.py
"""
Signal handlers for Notification lifecycle.

- When a Notification is created, schedule the background expansion task
  (process_notification_targets_task) AFTER DB commit to avoid race conditions.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Notification
from .tasks import process_notification_targets_task
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Notification)
def notification_post_save(sender, instance, created, **kwargs):
    """
    When a Notification is created, enqueue the expansion task after commit.
    Keep this signal lightweight — the heavy lifting happens in Celery.
    """
    if not created:
        return

    # schedule the expansion task after the transaction commits
    transaction.on_commit(lambda: process_notification_targets_task.delay(instance.pk))
    logger.debug("Scheduled process_notification_targets_task for Notification %s", instance.pk)
