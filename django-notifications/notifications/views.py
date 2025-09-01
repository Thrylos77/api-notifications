from datetime import timedelta
from django.utils import timezone
from django.shortcuts import get_object_or_404, render
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Notification
from .serializers import NotificationSerializer, NotificationListSerializer, NotificationLogSerializer
from drf_spectacular.utils import extend_schema, OpenApiParameter

# Create your views here.
class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    resource = "notification"
    permission_classes = [permissions.IsAuthenticated]

    permission_code_map = {
        "list_all": "list_all",
        "mark_read": "mark_read",
        "mark_unread": "mark_unread",
        "soft_delete": "soft_delete",
    }

    def get_queryset(self):
        user = self.request.user
        return self.queryset.filter(user=user, is_archived=False)
    
    def perform_create(self, serializer):
        """
        Assign the notification to the user who created it by default.
        Admins can override in the serializer if needed.
        """
        serializer.save(user=self.request.user)

    # Admin action to retrieve all notifications
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='is_archived', type=bool, location=OpenApiParameter.QUERY,
                description='Filter notifications by archived status (true/false)'
            )
        ]
    )
    @action(detail=False, methods=['get'], url_path='all', permission_classes=[permissions.IsAdminUser])
    def list_all(self, request):
        qs = self.queryset.all()

        is_archived = request.query_params.get('is_archived')
        if is_archived is not None:
            is_archived_bool = is_archived.lower() in ['true', '1']
            qs = qs.filter(is_archived=is_archived_bool)
        
        qs = self.filter_queryset(qs)
        serializer = NotificationListSerializer(qs, many=True)
        return Response(serializer.data)


    # Change the read status of a notification
    def _set_read_status(self, pk, read: bool):
        notification = get_object_or_404(
            self.queryset.filter(is_archived=False, user=self.request.user),
            pk=pk
        )
        if notification.is_read == read:
            return None
        notification.is_read = read
        notification.save(update_fields=['is_read'])
        return notification
    
    # Mark a notification as read
    @action(detail=True, methods=['post'], serializer_class=None, permission_classes=[permissions.IsAuthenticated])
    def mark_read(self, request, pk=None):
        notification = self._set_read_status(pk, True)
        if not notification:
            return Response({"detail": "Notification already marked as read."}, status=status.HTTP_409_CONFLICT)
        return Response({"detail": "Notification marked as read."}, status=status.HTTP_200_OK)

    # Mark a notification as unread
    @action(detail=True, methods=['post'], serializer_class=None, permission_classes=[permissions.IsAuthenticated])
    def mark_unread(self, request, pk=None):
        notification = self._set_read_status(pk, False)
        if not notification:
            return Response({"detail": "Notification already marked as unread."}, status=status.HTTP_409_CONFLICT)
        return Response({"detail": "Notification marked as unread."}, status=status.HTTP_200_OK)

    # Soft delete a notification
    @action(detail=True, methods=['delete'])
    def soft_delete(self, request, pk=None):
        # simple soft-delete: mark user as None or archived flag
        notification = get_object_or_404(self.queryset, pk=pk, user=request.user)
        if notification.is_archived:
            return Response({"detail": "Notification already deleted."}, status=status.HTTP_409_CONFLICT)
        notification.is_archived = True
        notification.archived_at = timezone.now()
        notification.save(update_fields=['is_archived', 'archived_at'])
        return Response({"detail": "Notification deleted."})

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='days', required=False, type=int, location=OpenApiParameter.QUERY,
                description='Delete archived notifications older than this number of days'
            )
        ]
    )
    @action(detail=False, methods=['delete'], url_path='purge-archived')
    def purge_archived(self, request):
        """
        Hard delete archived notifications older than a given number of days.
        Query param: ?days=<number_of_days>
        Default: 730 days = 2 years
        """
        days = int(request.query_params.get('days', 730))
        try:
            days_threshold = int(days) if days is not None else 730
        except ValueError:
            return Response(
                {"detail": "Invalid 'days' parameter. Must be an integer."},
                status=status.HTTP_400_BAD_REQUEST
            )
        threshold_date = timezone.now() - timedelta(days=days_threshold)

        deleted_count, _ = self.queryset.filter(is_archived=True, archived_at__lt=threshold_date).delete()
        return Response({"detail": f"{deleted_count} archived notifications deleted."}, status=status.HTTP_200_OK)


def index(request):
    return render(request, 'html/index.html')