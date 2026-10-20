from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserActivityLog


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display    = ('email', 'first_name', 'last_name', 'role', 'is_active', 'is_verified', 'date_joined')
    list_filter     = ('role', 'is_active', 'is_verified', 'is_staff')
    search_fields   = ('email', 'first_name', 'last_name', 'institution')
    ordering        = ('-date_joined',)
    readonly_fields = ('id', 'date_joined', 'last_login', 'last_login_ip', 'failed_login_attempts')

    fieldsets = (
        (None, {'fields': ('id', 'email', 'password')}),
        ('Personal', {'fields': ('first_name', 'last_name', 'institution', 'bio', 'avatar')}),
        ('Role & Access', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'is_verified')}),
        ('Security', {'fields': ('failed_login_attempts', 'locked_until', 'last_login_ip')}),
        ('Groups & Permissions', {'fields': ('groups', 'user_permissions'), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('date_joined', 'last_login')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields':  ('email', 'first_name', 'last_name', 'role', 'password1', 'password2'),
        }),
    )


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display  = ('user', 'action', 'ip_address', 'timestamp')
    list_filter   = ('action',)
    search_fields = ('user__email', 'ip_address')
    readonly_fields = ('id', 'timestamp')
    ordering      = ('-timestamp',)
