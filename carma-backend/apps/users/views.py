"""
CARMA — User Views (Auth + Profile)
"""
import logging
from django.utils import timezone
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema, OpenApiExample

from .models import User, UserActivityLog
from .serializers import (
    CARMATokenObtainPairSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
    UserAdminSerializer,
)
from .permissions import IsAdminUser

log  = logging.getLogger('carma')


def _get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log_activity(user, action, request, **metadata):
    try:
        UserActivityLog.objects.create(
            user       = user,
            action     = action,
            ip_address = _get_client_ip(request),
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500],
            metadata   = metadata,
        )
    except Exception as e:
        log.warning(f'Could not write activity log: {e}')


# ── Login throttle ─────────────────────────────────────────────
class LoginRateThrottle(AnonRateThrottle):
    scope = 'login'


# ── JWT Login ──────────────────────────────────────────────────
@extend_schema(
    summary='Obtain JWT token pair',
    description='Login with email + password. Returns access token, refresh token, and user profile.',
    tags=['Authentication'],
)
class CARMATokenObtainPairView(TokenObtainPairView):
    serializer_class    = CARMATokenObtainPairSerializer
    throttle_classes    = [LoginRateThrottle]
    permission_classes  = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            # Log successful login
            email = request.data.get('email', '')
            try:
                user = User.objects.get(email=email)
                user.last_login_ip = _get_client_ip(request)
                user.save(update_fields=['last_login_ip'])
                _log_activity(user, 'login', request)
            except User.DoesNotExist:
                pass
        return response


# ── Logout / Blacklist ─────────────────────────────────────────
@extend_schema(
    summary='Logout — blacklist refresh token',
    description='Blacklists the provided refresh token, invalidating the session.',
    tags=['Authentication'],
)
class TokenBlacklistView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'detail': 'Refresh token required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            _log_activity(request.user, 'logout', request)
            return Response({'detail': 'Successfully logged out.'},
                            status=status.HTTP_205_RESET_CONTENT)
        except TokenError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ── Register ───────────────────────────────────────────────────
@extend_schema(
    summary='Register a new user account',
    description='Creates a new CARMA user. Roles: researcher, reviewer, annotator. '
                'Admin accounts must be created by an existing admin.',
    tags=['Authentication'],
)
class RegisterView(generics.CreateAPIView):
    queryset            = User.objects.all()
    serializer_class    = RegisterSerializer
    permission_classes  = [permissions.AllowAny]
    throttle_classes    = [LoginRateThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Auto-login: issue tokens
        refresh = RefreshToken.for_user(user)
        _log_activity(user, 'register', request)

        return Response({
            'detail':  'Account created successfully.',
            'user':    UserProfileSerializer(user).data,
            'access':  str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)


# ── Current user (me) ──────────────────────────────────────────
@extend_schema(
    summary='Get / update current user profile',
    tags=['Users'],
)
class UserMeView(generics.RetrieveUpdateAPIView):
    serializer_class   = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        # Prevent users from elevating their own role
        if 'role' in request.data and not request.user.is_admin:
            return Response({'detail': 'You cannot change your own role.'},
                            status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)


# ── Change password ────────────────────────────────────────────
@extend_schema(
    summary='Change current user password',
    tags=['Users'],
)
class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        # Blacklist all existing refresh tokens (force re-login)
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
            for token in OutstandingToken.objects.filter(user=user):
                token.blacklistedtoken_set.get_or_create()
        except Exception:
            pass
        _log_activity(user, 'password_change', request)
        return Response({'detail': 'Password changed successfully. Please log in again.'},
                        status=status.HTTP_200_OK)


# ── Admin: user list ───────────────────────────────────────────
@extend_schema(
    summary='List all users (admin only)',
    tags=['Admin'],
)
class UserListView(generics.ListAPIView):
    queryset           = User.objects.all().order_by('-date_joined')
    serializer_class   = UserAdminSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    filterset_fields   = ['role', 'is_active', 'is_verified']
    search_fields      = ['email', 'first_name', 'last_name', 'institution']
    ordering_fields    = ['date_joined', 'last_login', 'email']


# ── Admin: user detail ─────────────────────────────────────────
@extend_schema(
    summary='Get / update / delete a user (admin only)',
    tags=['Admin'],
)
class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset           = User.objects.all()
    serializer_class   = UserAdminSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance == request.user:
            return Response({'detail': 'You cannot delete your own account.'},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)


# ── Health check ───────────────────────────────────────────────
@extend_schema(
    summary='Health check',
    description='Returns 200 OK when the API and database are reachable.',
    tags=['System'],
)
class HealthCheckView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from django.db import connection
        db_ok = True
        try:
            connection.ensure_connection()
        except Exception:
            db_ok = False

        payload = {
            'status':   'ok' if db_ok else 'degraded',
            'database': 'ok' if db_ok else 'unreachable',
            'version':  '1.0.0',
            'timestamp': timezone.now().isoformat(),
        }
        code = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(payload, status=code)
