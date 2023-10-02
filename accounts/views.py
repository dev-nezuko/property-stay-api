# bnbu_backend_api/account/views.py
from rest_framework import status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import RetrieveUpdateAPIView, RetrieveUpdateDestroyAPIView
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import PasswordChangeForm
from rest_framework.decorators import api_view, permission_classes
from django.contrib.auth.models import update_last_login
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from .serializers import FirstTimePasswordUpdateSerializer, UserSerializer, PasswordChangeSerializer, PasswordResetSerializer,CustomerSerializer
from .models import CustomUser
from django.contrib.auth.hashers import make_password
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

    
class UserListCreateView(APIView):
    permission_classes = [IsAdminUser]
    pagination_class = PageNumberPagination

    def get(self, request):
        paginator = self.pagination_class()
        users = CustomUser.objects.all().order_by('id')
        paginated_users = paginator.paginate_queryset(users, request)
        serializer = UserSerializer(paginated_users, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()
        # Newly created users should be active by default for the admin workflow.
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])

        return Response(serializer.data, status=status.HTTP_201_CREATED)

class UserDetailView(RetrieveUpdateDestroyAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]

    def put(self, request, *args, **kwargs):
        response = super().put(request, *args, **kwargs)
        return Response({"message": "User updated successfully"}, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        response = super().delete(request, *args, **kwargs)
        return Response({"message": "User deleted successfully"}, status=status.HTTP_204_NO_CONTENT) 

class ClientListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        clients = CustomUser.objects.filter(user_type='client').order_by('id')
        serializer = UserSerializer(clients, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class ClientDetailView(RetrieveUpdateDestroyAPIView):
    queryset = CustomUser.objects.filter(user_type='client')
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]

    def put(self, request, *args, **kwargs):
        response = super().put(request, *args, **kwargs)
        return Response({"message": "Client updated successfully"}, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        # Get the client object to be deleted
        client = self.get_object()

        # Get all customers associated with this client
        customers = CustomUser.objects.filter(client=client)

        # Delete all associated customers
        customers.delete()

        # Now delete the client
        self.perform_destroy(client)

        return Response({"message": "Client and associated customers deleted successfully"}, status=status.HTTP_204_NO_CONTENT)

class CustomerListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, client_id=None):
        if request.user.user_type == 'admin' and client_id is not None:
            # Admin views customers for a specific client
            client = get_object_or_404(CustomUser, id=client_id, user_type='client')
            customers = CustomUser.objects.filter(client=client, user_type='customer').order_by('id')
        elif request.user.user_type == 'admin':
            # Admin gets all customers with valid client association
            customers = CustomUser.objects.filter(user_type='customer').exclude(client__isnull=True).order_by('id')
        else:
            # Clients see only their own customers
            customers = CustomUser.objects.filter(client=request.user, user_type='customer').order_by('id')

        # Use CustomerSerializer to serialize the customer data
        serializer = CustomerSerializer(customers, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class CustomerCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, client_id):
        # Admin specifies client, otherwise client ID is set as the request user's ID
        if request.user.user_type == 'admin':
            request.data['client'] = client_id
        else:
            request.data['client'] = request.user.id

        # Ensure 'client' is present in the request data
        if not request.data.get('client'):
            return Response({"error": "Client ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Use the correct serializer for creating a Customer
        serializer = CustomerSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # Save the new customer instance
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CustomerDetailView(RetrieveUpdateDestroyAPIView):
    serializer_class = CustomerSerializer  # Use CustomerSerializer here
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # Fetch customer using primary key (pk)
        customer = get_object_or_404(CustomUser, pk=self.kwargs['pk'], user_type='customer')        
        # Allow admins to access any customer
        if self.request.user.user_type == 'admin':
            return customer        
        # Check if the customer is associated with the requesting client
        if customer.client != self.request.user:
            raise PermissionDenied("You do not have permission to access this customer.")        
        return customer

    def put(self, request, *args, **kwargs):
        # Retrieve the customer and check permissions
        customer = self.get_object()       
        # Update customer data using CustomerSerializer
        serializer = self.get_serializer(customer, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # Return a success message
        return Response({"message": "Customer updated successfully"}, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        # Retrieve the customer and check permissions
        customer = self.get_object()       
        # Perform deletion
        customer.delete()       
        # Return a success message for deletion
        return Response({"message": "Customer deleted successfully"}, status=status.HTTP_204_NO_CONTENT)
    
class FirstTimePasswordUpdateView(RetrieveUpdateAPIView):
    serializer_class = FirstTimePasswordUpdateSerializer  # Use the new serializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'pk'

    def get_queryset(self):
        return CustomUser.objects.all()

    def post(self, request, *args, **kwargs):
        user = self.get_object()

        # Ensure the authenticated user can only change their own password
        if request.user != user:
            return Response({"error": "You are not allowed to update this user's password."}, status=status.HTTP_403_FORBIDDEN)

        if not user.is_first_login:
            return Response({"error": "Password update not allowed. This is not your first login."}, status=status.HTTP_403_FORBIDDEN)

        # Use the serializer to validate and save the new password
        serializer = self.get_serializer(user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({"message": "Password updated successfully"}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def password_change(request):
    # Use the PasswordChangeSerializer to validate and save the new password
    serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response({"success": "Password changed successfully"}, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def password_reset(request):
    serializer = PasswordResetSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        user = CustomUser.objects.filter(email=email).first()
        if user:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            reset_link = f"http://example.com/reset/{uid}/{token}/"
            
            # Simulating sending the reset email (shows in console)
            send_mail(
                "Password Reset",
                f"Use this link to reset your password: {reset_link}",
                "from@example.com",
                [email],
            )
            
            return Response({"message": "Password reset email sent", "reset_link": reset_link}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class LoginView(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        user = CustomUser.objects.filter(email=email).first()  # Fetch user by email
        if user and user.check_password(password):  # Check if the password matches
            login(request, user)
            if user.is_first_login and user.user_type != 'admin':
                return Response({"message": "First login, password update required"}, status=status.HTTP_200_OK)
            return Response({"message": "Logged in successfully"}, status=status.HTTP_200_OK)
        return Response({"error": "Invalid email or password"}, status=status.HTTP_400_BAD_REQUEST)
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"message": "Logged out successfully"}, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    if request.user.user_type == 'admin':
        users = CustomUser.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    elif request.user.user_type == 'coach':
        return Response({"message": "Welcome to coach dashboard"}, status=status.HTTP_200_OK)
    elif request.user.user_type == 'research':
        return Response({"message": "Welcome to research dashboard"}, status=status.HTTP_200_OK)
    elif request.user.user_type == 'client':
        return Response({"message": "Welcome to client dashboard"}, status=status.HTTP_200_OK)
    else:
        return Response({"message": "Welcome to general dashboard"}, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    serializer = UserSerializer(request.user)
    return Response(serializer.data, status=status.HTTP_200_OK)
