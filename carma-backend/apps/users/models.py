"""
CARMA — Custom User Model
Extends AbstractBaseUser with role-based access control.
"""
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone


class UserManager(BaseUserManager):
    """Custom manager — email is the unique identifier, not username."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email address is required.')
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff',     True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role',         'admin')
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    CARMA User.
    Roles:
      admin      — full access, can manage users and approve constraint updates
      researcher — create/run experiments, build benchmarks
      reviewer   — review escalated cases, approve/reject plans
      annotator  — annotate gold adaptations, compute inter-annotator agreement
    """

    ROLE_CHOICES = [
        ('admin',      'Admin'),
        ('researcher', 'Researcher'),
        ('reviewer',   'Reviewer'),
        ('annotator',  'Annotator'),
    ]

    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Identity
    email      = models.EmailField(unique=True, db_index=True)
    username   = models.CharField(max_length=150, unique=True, blank=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name  = models.CharField(max_length=100, blank=True)

    # Role
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='researcher')

    # Status flags
    is_active    = models.BooleanField(default=True)
    is_staff     = models.BooleanField(default=False)
    is_verified  = models.BooleanField(default=False)  # email verified

    # Timestamps
    date_joined     = models.DateTimeField(default=timezone.now)
    last_login_ip   = models.GenericIPAddressField(null=True, blank=True)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until    = models.DateTimeField(null=True, blank=True)

    # Profile
    institution  = models.CharField(max_length=255, blank=True)
    bio          = models.TextField(blank=True)
    avatar       = models.ImageField(upload_to='avatars/', null=True, blank=True)

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()

    class Meta:
        db_table    = 'users'
        verbose_name        = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']
        indexes = [
            # NOTE: no index on ``email`` — the column is UNIQUE, which already
            # creates a unique index.  A second index would only cost writes.
            models.Index(fields=['role']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f'{self.email} ({self.role})'

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.email

    @property
    def is_admin(self):       return self.role == 'admin'
    @property
    def is_researcher(self):  return self.role in ('admin', 'researcher')
    @property
    def is_reviewer(self):    return self.role in ('admin', 'reviewer')
    @property
    def is_annotator(self):   return self.role in ('admin', 'annotator')

    def is_locked(self):
        """Account locked after 5 failed login attempts for 15 minutes."""
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False

    def record_failed_login(self):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            from datetime import timedelta
            self.locked_until = timezone.now() + timedelta(minutes=15)
        self.save(update_fields=['failed_login_attempts', 'locked_until'])

    def reset_login_attempts(self):
        if self.failed_login_attempts > 0:
            self.failed_login_attempts = 0
            self.locked_until = None
            self.save(update_fields=['failed_login_attempts', 'locked_until'])


class UserActivityLog(models.Model):
    """Tracks significant user actions for audit purposes."""
    ACTION_CHOICES = [
        ('login',           'Login'),
        ('logout',          'Logout'),
        ('register',        'Register'),
        ('password_change', 'Password Changed'),
        ('token_refresh',   'Token Refreshed'),
        ('failed_login',    'Failed Login'),
    ]

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs',
                                   null=True, blank=True)
    action     = models.CharField(max_length=30, choices=ACTION_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata   = models.JSONField(default=dict)
    timestamp  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_activity_logs'
        ordering = ['-timestamp']
        indexes  = [
            models.Index(fields=['user', 'action']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f'{self.user} — {self.action} @ {self.timestamp}'
