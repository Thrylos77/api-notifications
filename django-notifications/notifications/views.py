# notifications/views.py
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import get_object_or_404, render
from django.db import transaction

from rest_framework import viewsets, permissions, status, mixins
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .models import *
from .serializers import *

# -----------------------------------------------------------------------------------
# NotificationViewSet
# - Responsible for creation and management of Notification objects (the "message")
# - Creation will schedule background expansion of targets -> deliveries
# -----------------------------------------------------------------------------------
class NotificationViewSet(viewsets.ModelViewSet):
    """
    Admin/creator-facing ViewSet for Notification objects.
    - list/create/update/destroy for admins
    - creation uses NotificationCreateSerializer which triggers background expansion
    """
    queryset = Notification.objects.all()
    permission_classes = [permissions.IsAuthenticated]  # tighten as needed (admins/creators)
    resource = "notification"

    def get_serializer_class(self):
        if self.action == "create":
            return NotificationCreateSerializer
        if self.action == "list":
            return NotificationListSerializer
        return NotificationDetailSerializer
    """
    def get_queryset(self):
        user = self.request.user
        # By default show notifications created by the requesting user.
        # Administrators can override or you can extend this to allow listing all.
        if user.is_staff or user.is_superuser:
            return self.queryset.all()
        return self.queryset.filter(user=user)
    """
    def perform_create(self, serializer):
        """
        Save Notification. If no explicit user is provided, set the current user
        as the 'author' (backwards compatibility).
        """
        user = serializer.validated_data.get('user') if hasattr(serializer, 'validated_data') else None
        if not user:
            # Pass request.user as author by default
            serializer.save(user=self.request.user)
        else:
            serializer.save()

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAdminUser], url_path='all')
    def list_all(self, request):
        """
        Return all notifications (admin only). Accepts optional ?search params if needed.
        """
        qs = self.filter_queryset(self.get_queryset())
        serializer = NotificationSerializer(qs, many=True)
        return Response(serializer.data)

# -------------------------------------------------
# NotificationDeliveryViewSet (User-facing endpoints)
# -------------------------------------------------
class NotificationDeliveryViewSet(viewsets.GenericViewSet,
                      mixins.ListModelMixin,
                      mixins.RetrieveModelMixin
                      ):
    """
    Endpoints for recipients to manage their NotificationDeliveries.
    - list: list deliveries for the current authenticated user
    - retrieve: get a single delivery
    - partial_update: allow limited updates (e.g., ack)
    - mark_read / mark_unread: set is_read on the delivery
    - resend: admin-only action to requeue a delivery
    """
    queryset = NotificationDelivery.objects.all()
    serializer_class = NotificationDeliverySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Default queryset: deliveries for the current user.
        Assumes resolvers register recipients in namespace 'users' and use the user's PK as identifier.
        If your project uses a different namespace, adapt the logic here or pass ?namespace=...
        """
        user = self.request.user
        # allow admin to list all if explicitly requested
        if user.is_staff and self.request.query_params.get('all') == '1':
            return self.queryset

        # determine namespace/identifier for the current user
        # default namespace for simple setups is 'users' - change if your project uses another namespace
        namespace = self.request.query_params.get('namespace', 'users')
        identifier = str(user.pk)

        return self.queryset.filter(recipient_namespace=namespace, recipient_identifier=identifier).order_by("-created_at")

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def mark_read(self, request, pk=None):
        """
        Mark a delivery as read for the current user.
        """
        delivery = get_object_or_404(self.get_queryset(), pk=pk)
        if getattr(delivery, 'is_read', False):
            return Response({"detail": "Already marked as read."}, status=status.HTTP_409_CONFLICT)

        delivery.is_read = True
        delivery.save(update_fields=['is_read'])
        return Response({"detail": "Marked as read."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def mark_unread(self, request, pk=None):
        """
        Mark a delivery as unread for the current user.
        """
        delivery = get_object_or_404(self.get_queryset(), pk=pk)
        if not getattr(delivery, 'is_read', False):
            return Response({"detail": "Already marked as unread."}, status=status.HTTP_409_CONFLICT)

        delivery.is_read = False
        delivery.save(update_fields=['is_read'])
        return Response({"detail": "Marked as unread."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def resend(self, request, pk=None):
        """
        Admin-only: enqueue a resend of a given delivery (re-run send_delivery task).
        Useful for debugging or manual retries.
        """
        delivery = get_object_or_404(self.queryset, pk=pk)
        # schedule resend AFTER transaction commits to avoid race conditions
        from .tasks import send_notification_delivery_task
        transaction.on_commit(lambda: send_notification_delivery_task.delay(delivery.pk))
        return Response({"detail": "Resend scheduled."}, status=status.HTTP_200_OK)


class NotificationHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for Notification history (using django-simple-history).
    """
    queryset = Notification.history.all()
    # Keep the HistoricalNotificationSerializer you previously had (ensure it is updated to match new model)
    from .serializers import HistoricalNotificationSerializer
    serializer_class = HistoricalNotificationSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.query_params.get("user")
        if user:
            qs = qs.filter(user_id=user)
        return qs


def index(request):
    return render(request, "html/index.html")

