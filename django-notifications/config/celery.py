# config/celery.py
"""
Celery application initialization.

This module configures the Celery app for the Django project and enables task
auto-discovery. It should be imported by worker processes (e.g. `celery -A config.celery worker`).

What it does:
- Sets the default Django settings module for Celery.
- Creates a Celery instance named after the Django project (here: "config").
- Configures Celery to read settings from Django's settings module using the
  "CELERY_" prefix (namespace="CELERY").
- Autodiscovers tasks from installed Django apps so that @shared_task functions
  inside apps are registered automatically.
"""

import os
from celery import Celery

# Tell Celery which settings module to use
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Create the Celery app
app = Celery("config")

# Load configuration from Django settings, using the "CELERY_" namespace.
# Example: settings.CELERY_BROKER_URL is read as Celery config "broker_url".
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks across installed apps (looks for tasks.py)
app.autodiscover_tasks()
