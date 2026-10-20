"""
CARMA — Custom DRF Permissions
Role-based access control on top of JWT IsAuthenticated.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminUser(BasePermission):
    """Only admin role."""
    message = 'Administrator access required.'
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role == 'admin')


class IsResearcherOrAdmin(BasePermission):
    """Researcher or admin can create/run experiments."""
    message = 'Researcher or administrator access required.'
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ('admin', 'researcher'))


class IsReviewerOrAdmin(BasePermission):
    """Reviewer or admin can process escalations."""
    message = 'Reviewer or administrator access required.'
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ('admin', 'reviewer'))


class IsAnnotatorOrAdmin(BasePermission):
    """Annotator or admin can edit benchmark annotations."""
    message = 'Annotator or administrator access required.'
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ('admin', 'annotator'))


class IsOwnerOrAdmin(BasePermission):
    """Only the object owner or an admin can modify."""
    message = 'You do not have permission to modify this resource.'
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return request.user.is_authenticated
        return (request.user.role == 'admin'
                or getattr(obj, 'created_by_id', None) == request.user.id
                or getattr(obj, 'user_id', None) == request.user.id)


class ReadOnlyOrAdmin(BasePermission):
    """GET/HEAD/OPTIONS for any authenticated user; write only for admin."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role == 'admin'
