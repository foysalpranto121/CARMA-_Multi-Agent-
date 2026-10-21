"""
CARMA — Test settings.

The unit and API tests run against an in-memory SQLite database so they can
be executed without a PostgreSQL server.  The production and development
stack uses PostgreSQL (see ``config/settings.py``).

Run with::

    pytest                       # uses this module (see pytest.ini)
"""
from config.settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
        'TEST': {'NAME': ':memory:'},
    }
}

# Password hashing is the slowest part of the auth tests.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Throttling is disabled in tests: the rates are per-IP and would make the
# suite order-dependent (and fail on a shared machine).  The login endpoint
# declares its own throttle class, so the rate is raised instead of removed.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {
        'anon':  '1000/minute',
        'user':  '10000/minute',
        'login': '1000/minute',
    },
}

# No cache / broker side effects during tests.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

CHANNEL_LAYERS = {
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
