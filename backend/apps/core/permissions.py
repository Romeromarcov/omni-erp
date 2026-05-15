from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """Allow authenticated users to read; restrict writes to staff only."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_staff


class IsOwnerOrAdmin(permissions.BasePermission):
    """Allow object access to its owner or staff users."""

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        owner_field = getattr(view, "owner_field", "id_usuario")
        owner = getattr(obj, owner_field, None)
        if owner is None:
            return False
        owner_id = getattr(owner, "pk", owner)
        return owner_id == request.user.pk
