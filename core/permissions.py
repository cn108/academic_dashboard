"""Permission classes for the school management API."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import is_teacher


class IsTeacher(BasePermission):
    """Only teachers (and staff) may create or change school content."""

    message = "Only teachers can perform this action."

    def has_permission(self, request, view):
        return is_teacher(request.user)


class IsStaffOrReadOnly(BasePermission):
    """Classes and sessions are set up by the school office, not by teachers."""

    message = "Only school administrators can change this."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


class IsClassTeacherOrStaff(BasePermission):
    """Object-level: only the class teacher (or staff) may change a class."""

    message = "Only the class teacher can change this class."

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.can_manage(request.user)
