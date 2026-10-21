"""
CARMA — URL Configuration (Root)
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

# ── Auth / User views ──────────────────────────────────────────
from apps.users.views import (
    CARMATokenObtainPairView,
    TokenBlacklistView,
    RegisterView,
    UserMeView,
    ChangePasswordView,
    UserListView,
    UserDetailView,
    HealthCheckView,
)

# ── App views ──────────────────────────────────────────────────
from apps.processes.views import (
    ProcessViewSet, ConstraintSetViewSet,
    ConstraintViewSet, CorpusDocumentViewSet,
)
from apps.benchmark.views import (
    EventLogViewSet, CaseViewSet,
    BenchmarkScenarioViewSet, BenchmarkCaseViewSet,
    ImportLogView,
)
from apps.experiments.views import (
    ExperimentRunViewSet, RunConfigurationViewSet,
    RunResultViewSet, AdaptationViewSet,
    StartExperimentView, PauseExperimentView, ExportResultsView,
)
from apps.metrics.views import (
    RunMetricsViewSet, StatisticalTestsView, CostBreakdownView, ScenarioBreakdownView,
)
from apps.reviews.views import EscalationViewSet, HumanReviewViewSet
from apps.audit.views import AuditLogEntryViewSet, VerifyChainView, ReplayView

# ── Platform views ─────────────────────────────────────────────
from config.views import SystemStatusView

# ── DRF Router ─────────────────────────────────────────────────
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'processes',           ProcessViewSet,           basename='process')
router.register(r'constraint-sets',     ConstraintSetViewSet,     basename='constraint-set')
router.register(r'constraints',         ConstraintViewSet,        basename='constraint')
router.register(r'corpus',              CorpusDocumentViewSet,    basename='corpus')
router.register(r'event-logs',          EventLogViewSet,          basename='event-log')
router.register(r'cases',              CaseViewSet,               basename='case')
router.register(r'benchmark/scenarios', BenchmarkScenarioViewSet, basename='benchmark-scenario')
router.register(r'benchmark/cases',     BenchmarkCaseViewSet,     basename='benchmark-case')
router.register(r'experiments',         ExperimentRunViewSet,     basename='experiment')
router.register(r'run-configs',         RunConfigurationViewSet,  basename='run-config')
router.register(r'run-results',         RunResultViewSet,         basename='run-result')
router.register(r'adaptations',         AdaptationViewSet,        basename='adaptation')
router.register(r'metrics',             RunMetricsViewSet,        basename='metrics')
router.register(r'escalations',         EscalationViewSet,        basename='escalation')
router.register(r'reviews',             HumanReviewViewSet,       basename='review')
router.register(r'audit',              AuditLogEntryViewSet,      basename='audit')

# ── API v1 URL patterns ────────────────────────────────────────
api_v1_patterns = [
    # Auth
    path('auth/token/',           CARMATokenObtainPairView.as_view(), name='token-obtain'),
    path('auth/token/refresh/',   TokenRefreshView.as_view(),         name='token-refresh'),
    path('auth/token/verify/',    TokenVerifyView.as_view(),          name='token-verify'),
    path('auth/token/blacklist/', TokenBlacklistView.as_view(),       name='token-blacklist'),

    # Users
    path('users/register/',        RegisterView.as_view(),      name='user-register'),
    path('users/me/',              UserMeView.as_view(),        name='user-me'),
    path('users/change-password/', ChangePasswordView.as_view(),name='change-password'),
    path('users/',                 UserListView.as_view(),      name='user-list'),
    path('users/<uuid:pk>/',       UserDetailView.as_view(),    name='user-detail'),

    # Experiment actions
    path('experiments/<uuid:pk>/start/',  StartExperimentView.as_view(),  name='experiment-start'),
    path('experiments/<uuid:pk>/pause/',  PauseExperimentView.as_view(),  name='experiment-pause'),
    path('experiments/<uuid:pk>/export/', ExportResultsView.as_view(),    name='experiment-export'),

    # Metrics & stats
    path('metrics/statistical-tests/',  StatisticalTestsView.as_view(),  name='stats-tests'),
    path('metrics/cost-breakdown/',     CostBreakdownView.as_view(),     name='cost-breakdown'),
    path('metrics/scenario-breakdown/', ScenarioBreakdownView.as_view(), name='scenario-breakdown'),

    # Audit
    path('audit/verify-chain/',                     VerifyChainView.as_view(), name='audit-verify'),
    path('audit/replay/<uuid:adaptation_id>/',       ReplayView.as_view(),      name='audit-replay'),

    # Platform
    path('system/status/',            SystemStatusView.as_view(),     name='system-status'),

    # Benchmark import
    path('benchmark/import-log/', ImportLogView.as_view(), name='import-log'),

    # Router (all ViewSets)
    path('', include(router.urls)),
]

# ── Root URL patterns ──────────────────────────────────────────
urlpatterns = [
    # Django admin
    path('admin/', admin.site.urls),

    # API v1
    path('api/v1/', include((api_v1_patterns, 'api'), namespace='v1')),

    # OpenAPI / Swagger
    path('api/schema/', SpectacularAPIView.as_view(),                      name='schema'),
    path('api/docs/',   SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/',  SpectacularRedocView.as_view(url_name='schema'),   name='redoc'),

    # Health check
    path('health/', HealthCheckView.as_view(), name='health'),
]

# Serve media & static in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,  document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
