# notifications/tasks.py
"""
Celery tasks for notifications:
- process_notification_targets_task: expand NotificationTarget -> NotificationDelivery
- send_notification_delivery_task: send a single NotificationDelivery (WebSocket + Email)
"""

from celery import shared_task
from django.db import transaction
from django.template.loader import render_to_string
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging

from .models import Notification, NotificationDelivery
from .resolvers import resolve_target

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def process_notification_targets_task(self, notification_id):
    """
    Expand NotificationTarget rows into NotificationDelivery rows using resolvers.
    This task is idempotent: get_or_create is used to avoid duplicate deliveries.
    """
    try:
        notif = Notification.objects.get(pk=notification_id)
    except Notification.DoesNotExist:
        logger.warning("Notification %s not found - skipping expansion", notification_id)
        return

    targets = list(notif.targets.all())
    if not targets:
        logger.info("Notification %s has no targets", notification_id)
        return

    deliveries_created = 0
    # iterate targets and resolve recipients
    for t in targets:
        # The resolve_target helper handles missing resolvers, exceptions, and logging.
        # It ensures the correct arguments (including meta) are always passed.
        recipients = resolve_target(
            namespace=t.namespace,
            target_type=t.target_type,
            identifier=t.identifier,
            # Use getattr for safety, in case the 'meta' field hasn't been added to the model yet.
            meta=getattr(t, 'meta', {})
        )

        # create deliveries for each recipient
        for r in recipients:
            recipient_namespace = r.get('recipient_namespace') or t.namespace
            recipient_identifier = str(r.get('recipient_identifier'))
            recipient_email = r.get('email')
            recipient_channel = r.get('channel')

            # use get_or_create to be idempotent (unique constraint)
            obj, created = NotificationDelivery.objects.get_or_create(
                notification=notif,
                recipient_namespace=recipient_namespace,
                recipient_identifier=recipient_identifier,
                defaults={
                    'target': t,
                    'recipient_email': recipient_email,
                    'recipient_channel': recipient_channel
                }
            )
            if created:
                deliveries_created += 1
                # schedule send task AFTER transaction commit to ensure delivery exists in DB
                transaction.on_commit(lambda obj_pk=obj.pk: send_notification_delivery_task.delay(obj_pk))

    logger.info("Processed notification %s: deliveries_created=%d", notification_id, deliveries_created)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_notification_delivery_task(self, delivery_id):
    """
    Send a NotificationDelivery:
    - tries WebSocket (if recipient_channel present) — non-fatal if it fails
    - tries email (if recipient_email present) — retires on exception
    Update NotificationDelivery status with mark_sent()/mark_failed()
    """
    try:
        delivery = NotificationDelivery.objects.select_related('notification').get(pk=delivery_id)
    except NotificationDelivery.DoesNotExist:
        logger.warning("Delivery %s not found", delivery_id)
        return

    # record an attempt (increment attempts & last_attempt_at)
    delivery.mark_attempt()

    notification = delivery.notification

    # 1) WebSocket send (best-effort)
    ws_sent = False
    if delivery.recipient_channel:
        try:
            channel_layer = get_channel_layer()
            payload = {
                "type": "send_notification",
                "message": {
                    "id": notification.pk,
                    "title": notification.title,
                    "message": notification.message,
                    "meta": notification.meta,
                }
            }
            # synchronous wrapper since Celery tasks run in sync context
            async_to_sync(channel_layer.group_send)(delivery.recipient_channel, payload)
            ws_sent = True
            logger.debug("WebSocket payload sent to %s for delivery %s", delivery.recipient_channel, delivery_id)
        except Exception as e:
            # WS failure shouldn't prevent email attempts
            logger.exception("WebSocket send failed for delivery %s to channel %s: %s", delivery_id, delivery.recipient_channel, e)

    # 2) Email send (retriable)
    if delivery.recipient_email:
        try:
            subject = notification.title or f"Notification #{notification.pk}"
            context = {
                "first_name": delivery.recipient_identifier,
                "title": notification.title,
                "message": notification.message,
                "notification_id": notification.pk,
                "meta": notification.meta,
            }
            text_content = render_to_string("emails/notification.txt", context)
            html_content = render_to_string("emails/notification.html", context)

            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                to=[delivery.recipient_email],
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)

            # mark sent if email succeeded (and optionally ws succeeded too)
            delivery.mark_sent()
            logger.info("Delivery %s: email sent to %s", delivery_id, delivery.recipient_email)
            return

        except Exception as exc:
            logger.exception("Failed to send email for delivery %s to %s", delivery_id, delivery.recipient_email)
            try:
                # retry the task (Celery will re-raise a Retry)
                raise self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                # mark as failed when retries exhausted
                delivery.mark_failed(str(exc))
                logger.error("Max retries exceeded for delivery %s", delivery_id)
                return

    # If there is no email but WS was sent — treat as sent
    if not delivery.recipient_email and ws_sent:
        delivery.mark_sent()
        logger.info("Delivery %s: marked sent (WS only)", delivery_id)
        return

    # If neither channel nor email succeeded, mark failed
    if not delivery.recipient_email and not ws_sent:
        delivery.mark_failed("No channel and no email available or both failed")
        logger.warning("Delivery %s: no available channel/email", delivery_id)
