from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet, index

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    path('home/', index, name='index'),
    *router.urls,
]