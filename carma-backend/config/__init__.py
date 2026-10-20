"""CARMA package init — loads Celery on startup."""
from .celery import app as celery_app
__all__ = ('celery_app',)
