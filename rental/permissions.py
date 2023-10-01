from rest_framework import permissions

class IsSpecificUserType(permissions.BasePermission):
    """
    Custom permission to allow access based on specific user types.
    """

    def has_permission(self, request, view):
        # Check if the user is authenticated
        if request.user and request.user.is_authenticated:
            allowed_user_types = ['client', 'admin', 'research', 'coach', 'customer']
            # Allow access if the user type is in the allowed list
            return request.user.user_type in allowed_user_types
        return False


class IsAdminOrOwnData(permissions.BasePermission):
    """
    Custom permission to only allow admins to access all user data.
    Other users can only access their own data.
    """

    def has_permission(self, request, view):
        # Allow access to all users if they are authenticated
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Admin can access all objects
        if request.user.is_staff:
            return True
        # Non-admin users can access only their own data
        return obj.user == request.user
