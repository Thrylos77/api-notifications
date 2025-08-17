from django.contrib import admin
from .models import Notification

# Register your models here.

@admin.register(Notification)
class CustomNotification(admin.ModelAdmin):
    list_display = ('title', 'message', 'is_read', 'created_at', 'user')
    list_filter = ('is_read', 'created_at')
    search_fields = ('title', 'message')
    ordering = ('-created_at',)

