# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/rental/views.py
from django.http import StreamingHttpResponse
from rental.models import RentalProperty
from rental.serializers import RentalPropertySerializer
from rest_framework import viewsets, status
from rest_framework.decorators import action
from bnbu_constants.utility import (validate_file_type, file_to_df, validate_df, normalize_df,
                                    normalize_column, clean_price)
from rest_framework.response import Response
import bnbu_constants.constants as constants
from django.db.models import Max
from datetime import datetime, timedelta
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from .permissions import IsSpecificUserType, IsAdminOrOwnData
from rest_framework.permissions import IsAuthenticated
from rental.tasks import process_rental_properties_task
import csv
from celery.result import AsyncResult

class RentalPropertyPagination(PageNumberPagination):
    page_size = 10  # Default page size
    page_size_query_param = 'page_size'  # Query parameter to allow client to set the page size dynamically
    max_page_size = 100  # Maximum allowed page size for safety

    def get_page_size(self, request):
        # Get the page size from the query parameters
        page_size = request.query_params.get(self.page_size_query_param)

        # If no page size is provided, fallback to the default page size
        if page_size is None:
            return self.page_size

        try:
            page_size = int(page_size)
        except ValueError:
            # If the page size is not an integer, return the default page size
            return self.page_size

        # Ensure the page size does not exceed the maximum page size
        return min(page_size, self.max_page_size)

class RentalPropertyViewSet(viewsets.ModelViewSet):
    queryset = RentalProperty.objects.all().order_by('-created_at')
    permission_classes = [IsAuthenticated, IsSpecificUserType, IsAdminOrOwnData]
    serializer_class = RentalPropertySerializer
    pagination_class = RentalPropertyPagination


    @action(detail=False, methods=['post'], url_path='upload-properties')
    def upload_rental_properties(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"success": False, "message": "File not found"}, status=status.HTTP_400_BAD_REQUEST)

        if not validate_file_type(file):
            return Response({"success": False, "message": f"Invalid file type"}, status=status.HTTP_400_BAD_REQUEST)

        df = file_to_df(file)
        if df.empty:
            return Response({"success": False, "message": "File contains no data"}, status=status.HTTP_400_BAD_REQUEST)

        missing_cols = validate_df(df)
        if missing_cols:
            return Response({"success": False, "message": f"Missing columns: {missing_cols}"}, status=status.HTTP_400_BAD_REQUEST)

        normalize_column(df, "Ba")
        normalize_column(df, "Br")
        normalize_column(df, "Sq. ft.")
        df["Price"] = df["Price"].apply(clean_price)

        latest_batch = RentalProperty.objects.aggregate(Max('batch_id'))
        latest_batch_id = latest_batch['batch_id__max'] or 0
        new_batch_id = latest_batch_id + 1

        df = normalize_df(df)

        # Add user information to the data
        user = request.user
        context = {
            'user': user.id,
            'new_batch_id': new_batch_id
        }

        # Trigger Celery task
        task = process_rental_properties_task.delay(df.to_json(orient='records'), context)

        return Response({"success": True, "message": f"Batch {new_batch_id} processing started", "task_id": task.id}, status=status.HTTP_202_ACCEPTED)
    
    @action(detail=False, methods=['get'], url_path='task-result')
    def get_task_result(self, request):
        task_id = request.query_params.get("task_id")
        if not task_id:
            return Response({"success": False, "message": "Task ID is required"}, status=status.HTTP_400_BAD_REQUEST)
        task_result = AsyncResult(task_id)
        if task_result.state == "PENDING":
            return Response({"success": False, "message": "Task is still pending"}, status=status.HTTP_202_ACCEPTED)
        elif task_result.state == "FAILURE":
            return Response({"success": False, "message": "Task failed", "error": str(task_result.result)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        elif task_result.state == "SUCCESS":
            return Response({"success": True, "message": "Task completed", "result": task_result.result}, status=status.HTTP_200_OK)
        else:
            return Response({"success": True, "message": f"Task is {task_result.state}", "result": task_result.result}, status=status.HTTP_200_OK)
        
    @action(detail=False, methods=['get'], url_path='task-progress')
    def task_progress(self, request):
        task_id = request.query_params.get("task_id")
        if not task_id:
            return Response({"success": False, "message": "Task ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch task result using task_id
        task_result = AsyncResult(task_id)
        
        # Check the state of the task
        if task_result.state == "PENDING":
            return Response({"success": False, "state": "PENDING", "progress": 0}, status=status.HTTP_202_ACCEPTED)
        elif task_result.state == "PROGRESS":
            # If the task is in progress, send the current progress value
            return Response({
                "success": True,
                "state": "PROGRESS",
                "progress": task_result.info.get('progress', 0),
                "message": task_result.info.get('message', 'Processing...')
            }, status=status.HTTP_200_OK)
        elif task_result.state == "SUCCESS":
            # If the task is successfully completed, return the result
            return Response({
                "success": True,
                "state": "SUCCESS",
                "progress": 100,
                "result": task_result.info
            }, status=status.HTTP_200_OK)
        elif task_result.state == "FAILURE":
            # If the task failed, return the error message
            return Response({
                "success": False,
                "state": "FAILURE",
                "error": str(task_result.result)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            # Handle any other states that may occur
            return Response({
                "success": False,
                "state": task_result.state
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='all-properties')
    def all_properties(self, request):
        # Fetch all rental properties
        rental_properties = RentalProperty.objects.all().order_by('-created_at')
        
        # Paginate the results
        paginator = RentalPropertyPagination()
        paginated_properties = paginator.paginate_queryset(rental_properties, request)

        # Serialize the results
        serializer = self.get_serializer(paginated_properties, many=True)

        # Return paginated response
        return paginator.get_paginated_response(serializer.data)


    @action(detail=False, methods=['post'], url_path='filtered-list')
    def filtered_list(self, request):
        filters = request.data
        min_profit = filters.get("min_profit")
        max_profit = filters.get("max_profit")
        status = filters.get("status")
        batch_id = filters.get("batch_id")
        start_date = filters.get("start_date")
        end_date = filters.get("end_date")

        rental_properties = RentalProperty.objects.all()  # Initialize the queryset
        # print( '======')
        # print(rental_properties, '======')
        # Build the query
        query = Q()

        # Apply filters only if they are provided
        if min_profit is not None:
            query &= Q(monthly_estimated_profit__gte=min_profit)
        if max_profit is not None:
            query &= Q(monthly_estimated_profit__lte=max_profit)
        if status is not None:
            query &= Q(property_status=status)
        if batch_id is not None:
            query &= Q(batch_id=batch_id)

        # Handle start_date
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%B %d, %Y').date()
                query &= Q(created_at__gte=start_date)
            except ValueError:
                return Response({'detail': 'Invalid start date format. Use "Month day, year" (e.g., December 3, 2024).'}, 
                                status=status.HTTP_400_BAD_REQUEST)

        # Handle end_date
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%B %d, %Y').date()
                end_date = end_date + timedelta(days=1)  # Make the end_date exclusive
                query &= Q(created_at__lte=end_date)
            except ValueError:
                return Response({'detail': 'Invalid end date format. Use "Month day, year" (e.g., December 3, 2024).'},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            # end_date = datetime.now().date()
            end_date_str = datetime.now().strftime('%B %d, %Y')  # Convert current date to string
            end_date = datetime.strptime(end_date_str, '%B %d, %Y').date()  # Parse string back to date
            
        # If any filters are provided, apply them; otherwise, return all records
        if query != Q():  # Only apply filtering if there are valid filters
            rental_properties = rental_properties.filter(query).order_by('-created_at')
        else:
            rental_properties = rental_properties.order_by('-created_at')  # No filters, return all
        
        if self.request.user.is_staff:
            rental_properties = rental_properties.order_by('-created_at')
        else:   
            rental_properties = rental_properties.filter(user_id=self.request.user.id).order_by('-created_at')

        list_of_batch_ids = set()
        for property in rental_properties:
            list_of_batch_ids.add(property.batch_id)
        all_batch_ids = list(list_of_batch_ids)

        # Paginate the results
        paginator = RentalPropertyPagination()
        paginated_properties = paginator.paginate_queryset(rental_properties, request)

        # Serialize the results
        serializer = self.get_serializer(paginated_properties, many=True)
        
        # Include max_batch_id in the response
        response_data = {
            'all_batch_ids': all_batch_ids,
            'properties': serializer.data,
        }

        return paginator.get_paginated_response(response_data)
    
    @action(detail=False, methods=['get'], url_path='download-csv')
    def download_csv(self, request):
        filters = request.query_params
        min_profit = filters.get("min_profit")
        max_profit = filters.get("max_profit")
        status = filters.get("status")
        batch_id = filters.get("batch_id")
        start_date = filters.get("start_date")
        end_date = filters.get("end_date")

        rental_properties = RentalProperty.objects.all()  # Initialize the queryset
        query = Q()

        # Apply filters only if they are provided
        if min_profit is not None:
            query &= Q(monthly_estimated_profit__gte=min_profit)
        if max_profit is not None:
            query &= Q(monthly_estimated_profit__lte=max_profit)
        if status is not None:
            query &= Q(property_status=status)
        if batch_id is not None:
            query &= Q(batch_id=batch_id)

        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%B %d, %Y').date()
                query &= Q(created_at__gte=start_date)
            except ValueError:
                return Response({'detail': 'Invalid start date format. Use "Month day, year" (e.g., December 3, 2024).'}, 
                                status=status.HTTP_400_BAD_REQUEST)

        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%B %d, %Y').date()
                end_date = end_date + timedelta(days=1)  # Make the end_date exclusive
                query &= Q(created_at__lte=end_date)
            except ValueError:
                return Response({'detail': 'Invalid end date format. Use "Month day, year" (e.g., December 3, 2024).'},
                                status=status.HTTP_400_BAD_REQUEST)

        # Apply filters if any
        if query != Q():
            rental_properties = rental_properties.filter(query)
        else:
            rental_properties = rental_properties # No filters, return all

        if self.request.user.is_staff:
            rental_properties = rental_properties.order_by('-created_at')
        else:   
            rental_properties = rental_properties.filter(user_id=self.request.user.id).order_by('-created_at')


        # Prepare the CSV response
        response = StreamingHttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="rental_properties.csv"'

        # Define a generator to stream the CSV data
        def generate_csv():
            # Yield the header
            yield ",".join([
                "Date",
                "Batch Id",
                "Location",
                "Rent",
                "Bedrooms",
                "Bathrooms",
                "Square Feet",
                "Link",
                "Adr",
                "Utilities",
                "Estimated Profit",
                "Estimated Earnings",
                "Yearly Rent Cost",
                "Occupancy Rate",
                "Zillow Property Status"
            ]) + "\n"
    
            # Yield data rows one by one
            for property in rental_properties:
                # Escape the location field if necessary
                location = property.location
                # Enclose in quotes if there are commas or special characters (like '*', '#', etc.)
                if ',' in location or '"' in location or '*' in location or '#' in location:
                    location = '"{}"'.format(location.replace('"', '""'))

                # Handle the date field
                date = property.created_at.strftime('%B %d, %Y') if property.created_at else ""
                # Enclose in quotes if there are commas or special characters (like ',')
                if ',' in date or '"' in date:
                    date = '"{}"'.format(date.replace('"', '""'))

                yield ",".join([
                    date,
                    str(property.batch_id),
                    location,
                    str(property.rent),
                    str(property.no_of_bedrooms),
                    str(property.no_of_bathrooms),
                    str(property.square_feet),
                    property.property_zillow_link,
                    str(property.adr),
                    str(property.utilities),
                    str(property.monthly_estimated_profit),
                    str(property.yearly_projected_revenue),
                    str(property.yearly_rent_cost_util),
                    str(property.occupancy_rate),
                    property.property_status,
                ]) + "\n"

        # Stream the CSV data
        response.streaming_content = generate_csv()

        return response