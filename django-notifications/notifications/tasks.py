# notifications/tasks.py
"""
Celery tasks for notifications.

Primary task: send_notification_email_task
- Fetches Notification from DB (using ID) to ensure fresh data.
- Creates a NotificationLog entry with status updates.
- Renders plain-text and HTML templates for the email body.
- Sends email using Django's EmailMultiAlternatives.
- Uses Celery retry mechanism on transient failures.
- Should be idempotent when possible (if send is retried, logs reflect attempts).

Notes on robustness:
- task.bind=True allows access to self.retry for retrying.
- max_retries and default_retry_delay control retry behavior.
- Exceptions are logged and saved in NotificationLog.detail for debugging.
"""

from celery import shared_task
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone
import logging

from .models import Notification, NotificationLog

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_notification_email_task(self, notification_id):
    """
    Celery task that sends an email for a Notification instance.

    Args:
        notification_id (int): primary key of the Notification to send.

    Behavior:
    - If the Notification does not exist, the task returns quietly.
    - If the user has no email, it logs and returns.
    - It creates a NotificationLog with status 'pending' before sending.
    - If sending succeeds: NotificationLog is updated to 'sent'.
    - If sending fails: NotificationLog is updated to 'failed' and the task retries.
    """
    try:
        notif = Notification.objects.select_related('user').get(pk=notification_id)
    except Notification.DoesNotExist:
        # If the notification was deleted before the task ran, nothing to do.
        logger.warning("Notification %s does not exist anymore.", notification_id)
        return

    user = notif.user
    recipient_email = getattr(user, 'email', None)
    if not recipient_email:
        # Create a log entry so we know why it wasn't sent
        NotificationLog.objects.create(
            notification=notif,
            channel='email',
            status='failed',
            detail='No recipient email available'
        )
        logger.warning("User %s has no email. Skipping notification %s.", user, notification_id)
        return

    # Create a pending log entry
    log = NotificationLog.objects.create(
        notification=notif,
        channel='email',
        status='pending',
        detail='Queued for delivery',
    )

    # Prepare email content using templates (text + html)
    context = {
        "first_name": getattr(user, "first_name", user.username),
        "title": notif.title,
        "message": notif.message,
        "notification_id": notif.pk,
    }

    subject = f"New notification from {settings.DEFAULT_FROM_EMAIL}"
    text_content = render_to_string("emails/notification.txt", context)
    html_content = render_to_string("emails/notification.html", context)

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email],
        )
        msg.attach_alternative(html_content, "text/html")
        # send() may raise exceptions on SMTP failure
        msg.send(fail_silently=False)

        # Update the log to 'sent'
        log.status = 'sent'
        log.detail = f"Sent at {timezone.now().isoformat()}"
        log.save()

        logger.info("Notification %s sent to %s", notification_id, recipient_email)

    except Exception as exc:
        # Update log with failure details
        log.status = 'failed'
        log.detail = str(exc)
        log.save()

        logger.exception("Failed to send notification %s to %s", notification_id, recipient_email)

        # Retry the task using Celery retry mechanism for transient errors.
        # This will re-raise a Retry exception and schedule a retry.
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            # Max retries reached: leave the log as failed and do not rethrow
            logger.error("Max retries exceeded for notification %s", notification_id)
            return

