# from rest_framework import permissions

# # class IsAdminUser(permissions.BasePermission):
# #     """
# #     Allows access only to admin users.
# #     """
# #     def has_permission(self, request, view):
# #         return request.user and request.user.is_authenticated and request.user.user_type == 'admin'

# class IsAdminUser(permissions.BasePermission):
#     """
#     Allows access only to admin users.
#     """
#     def has_permission(self, request, view):
#         return request.user.is_authenticated and request.user.user_type == 'admin'

# class IsFirstLogin(permissions.BasePermission):
#     """
#     Allows access if it is the user's first login and they must change their password.
#     """
#     def has_permission(self, request, view):
#         return request.user.is_authenticated and request.user.is_first_login



# class IsResearchUser(permissions.BasePermission):
#     """
#     Allows access only to research users.
#     """
#     def has_permission(self, request, view):
#         return request.user and request.user.is_authenticated and request.user.user_type == 'research'


# class IsCoachUser(permissions.BasePermission):
#     """
#     Allows access only to coach users.
#     """
#     def has_permission(self, request, view):
#         return request.user and request.user.is_authenticated and request.user.user_type == 'coach'


# class IsClientUser(permissions.BasePermission):
#     """
#     Allows access only to client users.
#     """
#     def has_permission(self, request, view):
#         return request.user and request.user.is_authenticated and request.user.user_type == 'client'


# class IsGeneralUser(permissions.BasePermission):
#     """
#     Allows access only to general users.
#     """
#     def has_permission(self, request, view):
#         return request.user and request.user.is_authenticated and request.user.user_type == 'general'
