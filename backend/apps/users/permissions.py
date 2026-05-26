from rest_framework.permissions import BasePermission

from .models import Role


class _RoleRequired(BasePermission):
    role = ""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == self.role)


class IsResident(_RoleRequired):
    role = Role.RESIDENT


class IsFaculty(_RoleRequired):
    role = Role.FACULTY


class IsAdmin(_RoleRequired):
    role = Role.ADMIN
