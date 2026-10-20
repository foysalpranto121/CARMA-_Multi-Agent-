"""
CARMA — User serializers
Includes custom JWT token pair with extra claims.
"""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from apps.users.models import User


# ── JWT with extra claims ──────────────────────────────────────
class CARMATokenObtainPairSerializer(TokenObtainPairSerializer):
    """Embeds user role, name and email directly into the JWT payload."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Custom claims injected into access token
        token['email']      = user.email
        token['role']       = user.role
        token['first_name'] = user.first_name
        token['last_name']  = user.last_name
        token['is_verified']= user.is_verified
        return token

    def validate(self, attrs):
        # Check account lock before calling super()
        email = attrs.get(self.username_field, '')
        try:
            user = User.objects.get(email=email)
            if user.is_locked():
                raise serializers.ValidationError(
                    {'detail': 'Account locked due to too many failed attempts. Try again later.'}
                )
        except User.DoesNotExist:
            pass  # Let super() handle invalid credentials

        try:
            data = super().validate(attrs)
        except Exception:
            # Record failed attempt
            try:
                user = User.objects.get(email=email)
                user.record_failed_login()
            except User.DoesNotExist:
                pass
            raise

        # Reset on success
        self.user.reset_login_attempts()
        self.user.last_login = timezone.now()
        self.user.save(update_fields=['last_login'])

        # Embed user data in response (in addition to tokens)
        data['user'] = UserProfileSerializer(self.user).data
        return data


# ── User profile ───────────────────────────────────────────────
class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'full_name', 'role', 'is_verified', 'institution',
            'bio', 'avatar', 'date_joined',
        ]
        read_only_fields = ['id', 'email', 'is_verified', 'date_joined']

    def get_full_name(self, obj):
        return obj.get_full_name()


# ── Registration ───────────────────────────────────────────────
class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(
        write_only=True, required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password2 = serializers.CharField(
        write_only=True, required=True,
        style={'input_type': 'password'},
        label='Confirm Password'
    )

    class Meta:
        model  = User
        fields = [
            'email', 'username', 'first_name', 'last_name',
            'password', 'password2', 'role', 'institution',
        ]
        extra_kwargs = {
            'first_name':  {'required': True},
            'last_name':   {'required': True},
            'role':        {'required': False},
            'institution': {'required': False},
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})

        # Prevent public self-registration as admin
        if attrs.get('role') == 'admin':
            raise serializers.ValidationError(
                {'role': 'Admin accounts must be created by an existing administrator.'}
            )
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')

        # Auto-generate username from email if not provided
        if not validated_data.get('username'):
            base = validated_data['email'].split('@')[0]
            username = base
            count = 1
            while User.objects.filter(username=username).exists():
                username = f'{base}{count}'
                count += 1
            validated_data['username'] = username

        user = User.objects.create_user(password=password, **validated_data)
        return user


# ── Change password ────────────────────────────────────────────
class ChangePasswordSerializer(serializers.Serializer):
    old_password  = serializers.CharField(required=True, write_only=True,
                                          style={'input_type': 'password'})
    new_password  = serializers.CharField(required=True, write_only=True,
                                          validators=[validate_password],
                                          style={'input_type': 'password'})
    new_password2 = serializers.CharField(required=True, write_only=True,
                                          style={'input_type': 'password'})

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({'new_password': 'New passwords do not match.'})
        return attrs

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value


# ── Admin user list ────────────────────────────────────────────
class UserAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'role', 'is_active', 'is_verified', 'institution',
            'date_joined', 'last_login', 'failed_login_attempts',
        ]
        read_only_fields = ['id', 'date_joined', 'last_login']
