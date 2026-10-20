"""CARMA — ASGI config (Daphne + Django Channels)"""
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from django.urls import re_path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_asgi_app = get_asgi_application()

# Import consumers after Django setup
from apps.audit.consumers    import ExperimentLogConsumer
from apps.reviews.consumers  import ReviewConsumer

websocket_urlpatterns = [
    re_path(r'^ws/experiments/(?P<run_id>[0-9a-f-]+)/logs/$', ExperimentLogConsumer.as_asgi()),
    re_path(r'^ws/cases/(?P<case_id>[0-9a-f-]+)/live/$',      ExperimentLogConsumer.as_asgi()),
    re_path(r'^ws/reviews/$',                                  ReviewConsumer.as_asgi()),
]

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
