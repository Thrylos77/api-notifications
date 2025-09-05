from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'notifications/deliveries', NotificationDeliveryViewSet, basename='notification-delivery')
# History (Admin)
router.register(r'notifications/history', NotificationHistoryViewSet, basename='notification-history')

urlpatterns = [
    path('home/', index, name='index'),
    *router.urls,
]