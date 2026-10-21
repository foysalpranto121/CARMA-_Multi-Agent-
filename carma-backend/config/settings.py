"""
CARMA Backend — Django Settings
Database: PostgreSQL (CARMADB)
Auth: JWT via djangorestframework-simplejwt
"""
import os
import warnings
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv
from django.core.management.utils import get_random_secret_key

# ── Paths ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ── Security ───────────────────────────────────────────────────
# No secret is committed to the repository.  When SECRET_KEY is absent a random
# key is generated for this process, which is fine for development but invalidates
# existing tokens on every restart — set SECRET_KEY in .env for a stable install.
SECRET_KEY = config('SECRET_KEY', default='')
if not SECRET_KEY:
    SECRET_KEY = get_random_secret_key()
    warnings.warn(
        'SECRET_KEY is not set — a random key was generated for this process. '
        'Set SECRET_KEY in .env so sessions and tokens survive a restart.',
        RuntimeWarning,
    )

DEBUG       = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost', cast=Csv())

# ── Application Definition ─────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'channels',
    'django_celery_results',
    'django_celery_beat',
    'drf_spectacular',
]

LOCAL_APPS = [
    'apps.users',
    'apps.processes',
    'apps.benchmark',
    'apps.experiments',
    'apps.metrics',
    'apps.reviews',
    'apps.audit',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ── Middleware ─────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',          # must be high
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.users.middleware.RequestLoggingMiddleware',  # custom
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ── ASGI (WebSocket via Channels) ──────────────────────────────
ASGI_APPLICATION = 'config.asgi.application'
WSGI_APPLICATION = 'config.wsgi.application'

# ── Database — PostgreSQL ──────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     config('DB_NAME',     default='CARMADB'),
        'USER':     config('DB_USER',     default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST':     config('DB_HOST',     default='localhost'),
        'PORT':     config('DB_PORT',     default='5432'),
        'OPTIONS': {
            'connect_timeout': 10,
            'options':         '-c search_path=public',
        },
        'CONN_MAX_AGE': 60,   # persistent connections
        'TEST': {
            'NAME': 'CARMADB_test',
        },
    }
}

# ── Custom User Model ──────────────────────────────────────────
AUTH_USER_MODEL = 'users.User'

# ── Password Validation ────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Use Argon2 password hashing (most secure)
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

# ── REST Framework ─────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon':  '100/hour',
        'user':  '2000/hour',
        'login': '10/minute',      # custom scope for login endpoint
    },
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    'EXCEPTION_HANDLER': 'apps.users.exceptions.custom_exception_handler',
}

# ── JWT Configuration ──────────────────────────────────────────
SIMPLE_JWT = {
    # Token lifetimes
    'ACCESS_TOKEN_LIFETIME':  timedelta(
        minutes=config('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', default=60, cast=int)
    ),
    'REFRESH_TOKEN_LIFETIME': timedelta(
        days=config('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=7, cast=int)
    ),

    # Rotation & blacklisting
    'ROTATE_REFRESH_TOKENS':      True,
    'BLACKLIST_AFTER_ROTATION':   True,
    'UPDATE_LAST_LOGIN':          True,

    # Algorithm
    'ALGORITHM':                  'HS256',
    'SIGNING_KEY':                config('JWT_SIGNING_KEY', default='') or SECRET_KEY,
    'VERIFYING_KEY':              None,
    'AUDIENCE':                   None,
    'ISSUER':                     'carma-platform',

    # Headers
    'AUTH_HEADER_TYPES':          ('Bearer',),
    'AUTH_HEADER_NAME':           'HTTP_AUTHORIZATION',

    # Token claim fields
    'USER_ID_FIELD':              'id',
    'USER_ID_CLAIM':              'user_id',

    # Custom claims serializer
    'TOKEN_OBTAIN_SERIALIZER':    'apps.users.serializers.CARMATokenObtainPairSerializer',
    'TOKEN_REFRESH_SERIALIZER':   'rest_framework_simplejwt.serializers.TokenRefreshSerializer',
    'TOKEN_VERIFY_SERIALIZER':    'rest_framework_simplejwt.serializers.TokenVerifySerializer',
    'TOKEN_BLACKLIST_SERIALIZER': 'rest_framework_simplejwt.serializers.TokenBlacklistSerializer',
}

# ── CORS ───────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:5173',
    cast=Csv()
)
CORS_ALLOW_CREDENTIALS    = True
CORS_EXPOSE_HEADERS       = ['Content-Disposition']
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization',
    'content-type', 'dnt', 'origin', 'user-agent',
    'x-csrftoken', 'x-requested-with',
]

# ── Security Headers ───────────────────────────────────────────
if not DEBUG:
    SECURE_HSTS_SECONDS           = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD           = True
    SECURE_SSL_REDIRECT           = True
    SESSION_COOKIE_SECURE         = True
    CSRF_COOKIE_SECURE            = True
    SECURE_CONTENT_TYPE_NOSNIFF   = True
    X_FRAME_OPTIONS               = 'DENY'
    SECURE_REFERRER_POLICY        = 'strict-origin-when-cross-origin'

# ── Channels (WebSocket) ───────────────────────────────────────
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [config('REDIS_URL', default='redis://localhost:6379/0')],
            'capacity':    1500,
            'expiry':      10,
        },
    },
}

# ── Celery ─────────────────────────────────────────────────────
CELERY_BROKER_URL            = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND        = 'django-db'
CELERY_CACHE_BACKEND         = 'default'
CELERY_ACCEPT_CONTENT        = ['json']
CELERY_TASK_SERIALIZER       = 'json'
CELERY_RESULT_SERIALIZER     = 'json'
CELERY_TIMEZONE              = 'UTC'
CELERY_TASK_TRACK_STARTED    = True
CELERY_TASK_TIME_LIMIT       = 3600          # 1 hour max per task
CELERY_TASK_SOFT_TIME_LIMIT  = 3300
CELERY_WORKER_MAX_TASKS_PER_CHILD = 50       # prevent memory leaks
CELERY_BEAT_SCHEDULER        = 'django_celery_beat.schedulers:DatabaseScheduler'

# ── Caching ────────────────────────────────────────────────────
CACHES = {
    'default': {
        'BACKEND':  'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://localhost:6379/0'),
        'TIMEOUT':  300,
        'KEY_PREFIX': 'carma',
    }
}

# ── API Schema (drf-spectacular) ───────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE':       'CARMA Research Platform API',
    'DESCRIPTION': (
        'Constraint-Aware Retrieval and Multi-Agent Workflow Adaptation. '
        'Provides endpoints for process frames, WF-Adapt benchmark, '
        'experiment orchestration, metrics, human review, and audit logging.'
    ),
    'VERSION':     '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SECURITY': [{'jwtAuth': []}],
    'COMPONENT_SPLIT_REQUEST': True,
    'ENUM_GENERATE_CHOICE_DESCRIPTION': True,
    'SCHEMA_PATH_PREFIX': r'/api/v1/',
    'SERVERS': [
        {'url': 'http://localhost:8000', 'description': 'Development'},
    ],
}

# ── Internationalization ───────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'UTC'
USE_I18N      = True
USE_TZ        = True

# ── Static / Media ─────────────────────────────────────────────
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL   = '/media/'
MEDIA_ROOT  = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Logging ────────────────────────────────────────────────────
(BASE_DIR / 'logs').mkdir(parents=True, exist_ok=True)

try:
    import pythonjsonlogger.jsonlogger  # noqa: F401
    _JSON_FORMATTER = {
        '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
        'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
    }
except ImportError:
    _JSON_FORMATTER = {
        'format': '[{asctime}] {levelname} {name}: {message}',
        'style': '{',
    }

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': _JSON_FORMATTER,
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style':  '{',
        },
    },
    'handlers': {
        'console': {
            'class':     'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class':     'logging.handlers.RotatingFileHandler',
            'filename':  BASE_DIR / 'logs' / 'carma.log',
            'maxBytes':  10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level':    'INFO',
    },
    'loggers': {
        'django':          {'handlers': ['console', 'file'], 'level': 'WARNING', 'propagate': False},
        'django.db.backends': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'carma':           {'handlers': ['console', 'file'], 'level': 'DEBUG' if DEBUG else 'INFO', 'propagate': False},
        'celery':          {'handlers': ['console'], 'level': 'INFO',    'propagate': False},
    },
}

# ── Email ──────────────────────────────────────────────────────
EMAIL_BACKEND      = 'django.core.mail.backends.console.EmailBackend' if DEBUG \
                     else 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST         = config('EMAIL_HOST',     default='smtp.gmail.com')
EMAIL_PORT         = config('EMAIL_PORT',     default=587,   cast=int)
EMAIL_USE_TLS      = config('EMAIL_USE_TLS',  default=True,  cast=bool)
EMAIL_HOST_USER    = config('EMAIL_HOST_USER',    default='')
EMAIL_HOST_PASSWORD= config('EMAIL_HOST_PASSWORD',default='')
DEFAULT_FROM_EMAIL = 'CARMA Platform <noreply@carma.ai>'

FRONTEND_URL       = config('FRONTEND_URL', default='http://localhost:5173')

# ── CARMA Engine Settings ──────────────────────────────────────
QDRANT_URL     = config('QDRANT_URL',     default='http://localhost:6333')
QDRANT_API_KEY = config('QDRANT_API_KEY', default='')
OPENAI_API_KEY = config('OPENAI_API_KEY', default='')
OLLAMA_BASE_URL= config('OLLAMA_BASE_URL',default='http://localhost:11434')
OPENAI_BASE_URL= config('OPENAI_BASE_URL',default='https://api.openai.com/v1')

# HMAC secret used to sign the SCV execution tokens.
SCV_SIGNING_SECRET = config('SCV_SIGNING_SECRET', default=SECRET_KEY)
