"""
Import Celery app to ensure tasks are automatically 
discovered when Django starts.
This makes sure .delay() calls 
work correctly for all registered tasks.
"""
from .celery import app as celery_app

__all__ = ("celery_app",)
