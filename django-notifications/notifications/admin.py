# notifications/admin.py
"""
Django admin configuration for the notifications app.

- Register Notification with history support (django-simple-history).
- Provide inlines for NotificationTarget and NotificationDelivery.
- Add admin actions to trigger expansion (create deliveries) and to resend deliveries.
- Include helpful list_display, filters and search fields for easier debugging.
"""

from django.contrib import admin
from django.db import transaction
from django.utils.html import format_html
from django.utils import timezone

from simple_history.admin import SimpleHistoryAdmin

from .models import Notification, NotificationTarget, NotificationDelivery
from .tasks import process_notification_targets_task, send_notification_delivery_task

# -------------------------
# Inlines
# -------------------------
class NotificationTargetInline(admin.TabularInline):
    """Inline display for NotificationTarget rows linked to a Notification."""
    model = NotificationTarget
    extra = 0
    readonly_fields = ("namespace", "target_type", "identifier", "meta", "created_at")
    can_delete = False
    verbose_name = "Target"
    verbose_name_plural = "Targets"


class NotificationDeliveryInline(admin.TabularInline):
    """Inline display for NotificationDelivery rows linked to a Notification."""
    model = NotificationDelivery
    extra = 0
    readonly_fields = (
        "recipient_namespace", "recipient_identifier", "recipient_email",
        "recipient_channel", "status", "attempts", "last_attempt_at",
        "delivered_at", "error", "created_at", "is_read"
    )
    fields = readonly_fields
    can_delete = False
    verbose_name = "Delivery"
    verbose_name_plural = "Deliveries"


# -------------------------
# Admin actions (Delivery)
# -------------------------
@admin.action(description="Mark selected deliveries as SENT")
def mark_deliveries_sent(modeladmin, request, queryset):
    """Admin action to mark selected deliveries as sent (sets delivered_at)."""
    for d in queryset:
        d.mark_sent()
    modeladmin.message_user(request, f"{queryset.count()} deliveries marked as sent.")


@admin.action(description="Mark selected deliveries as FAILED (provide reason)")
def mark_deliveries_failed(modeladmin, request, queryset):
    """
    Mark deliveries as failed. This action will mark_failed with a default message.
    For a more detailed message, consider editing the delivery directly.
    """
    reason = "Marked as failed by admin"
    for d in queryset:
        d.mark_failed(reason)
    modeladmin.message_user(request, f"{queryset.count()} deliveries marked as failed.")


@admin.action(description="Resend selected deliveries (enqueue send task)")
def resend_selected_deliveries(modeladmin, request, queryset):
    """
    Enqueue the Celery send task for each selected delivery.
    We schedule the task after transaction commit to avoid race conditions.
    """
    enqueued = 0
    for d in queryset:
        transaction.on_commit(lambda pk=d.pk: send_notification_delivery_task.delay(pk))
        enqueued += 1
    modeladmin.message_user(request, f"Enqueued resend for {enqueued} deliveries.")


@admin.action(description="Mark selected deliveries as READ")
def mark_deliveries_read(modeladmin, request, queryset):
    updated = queryset.update(is_read=True)
    modeladmin.message_user(request, f"{updated} deliveries marked as read.")


@admin.action(description="Mark selected deliveries as UNREAD")
def mark_deliveries_unread(modeladmin, request, queryset):
    updated = queryset.update(is_read=False)
    modeladmin.message_user(request, f"{updated} deliveries marked as unread.")


# -------------------------
# Delivery admin
# -------------------------
@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    """Admin for NotificationDelivery rows (per-recipient)."""
    list_display = (
        "id", "short_notification", "recipient_namespace", "recipient_identifier",
        "recipient_email", "recipient_channel", "status", "attempts", "is_read", "created_at"
    )
    list_filter = ("status", "recipient_namespace", "is_read")
    search_fields = ("recipient_identifier", "recipient_email", "notification__title", "error")
    readonly_fields = (
        "notification", "target", "recipient_namespace", "recipient_identifier",
        "recipient_email", "recipient_channel", "status", "attempts",
        "last_attempt_at", "delivered_at", "error", "created_at"
    )
    actions = [
        mark_deliveries_sent,
        mark_deliveries_failed,
        resend_selected_deliveries,
        mark_deliveries_read,
        mark_deliveries_unread,
    ]

    def short_notification(self, obj):
        """Short representation of related notification (title with link)."""
        if not obj.notification:
            return "-"
        return format_html(
            '<a href="{}">#{}: {}</a>',
            f"/admin/notifications/notification/{obj.notification.pk}/change/",
            obj.notification.pk,
            (obj.notification.title[:60] + '...') if len(obj.notification.title) > 60 else obj.notification.title
        )
    short_notification.short_description = "Notification"


# -------------------------
# Notification admin
# -------------------------
@admin.action(description="Expand targets into deliveries (enqueue expansion task)")
def expand_targets_action(modeladmin, request, queryset):
    """
    Enqueue the process_notification_targets_task for each selected Notification.
    Tasks are scheduled after transaction commit for safety.
    """
    enqueued = 0
    for notif in queryset:
        transaction.on_commit(lambda nid=notif.pk: process_notification_targets_task.delay(nid))
        enqueued += 1
    modeladmin.message_user(request, f"Enqueued expansion for {enqueued} notifications.")


@admin.register(Notification)
class NotificationAdmin(SimpleHistoryAdmin):
    """Admin for Notification objects with inline targets and deliveries."""
    list_display = ("id", "title", "short_message", "created_at", "author", "deliveries_count")
    search_fields = ("title", "message", "meta", "user__email", "user__username")
    list_filter = ("created_at",)
    inlines = [NotificationTargetInline, NotificationDeliveryInline]
    readonly_fields = ("created_at",)
    actions = [expand_targets_action]

    def short_message(self, obj):
        return (obj.message[:80] + '...') if obj.message and len(obj.message) > 80 else obj.message
    short_message.short_description = "Message"

    def author(self, obj):
        return getattr(obj.user, "email", None) or getattr(obj.user, "username", None)
    author.short_description = "Author"

    def deliveries_count(self, obj):
        return obj.deliveries.count()
    deliveries_count.short_description = "Deliveries"


# -------------------------
# NotificationTarget admin (optional, read-only)
# -------------------------
@admin.register(NotificationTarget)
class NotificationTargetAdmin(admin.ModelAdmin):
    """Simple admin for NotificationTarget - mostly read-only for inspection."""
    list_display = ("id", "notification", "namespace", "target_type", "identifier", "created_at")
    search_fields = ("identifier", "namespace", "notification__title")
    readonly_fields = ("notification", "namespace", "target_type", "identifier", "meta", "created_at")
    list_filter = ("namespace", "target_type")
    ordering = ("-created_at",)
