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
from datetime import datetime
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from .permissions import IsSpecificUserType, IsAdminOrOwnData
from rest_framework.permissions import IsAuthenticated
from rental.tasks import process_rental_properties_task
import csv
import zipfile

import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException
from celery.result import AsyncResult
from django.core.cache import cache
from rest_framework.exceptions import PermissionDenied, ValidationError
from decimal import Decimal, InvalidOperation

CSV_HEADER = [
    "Date", "Batch Id", "Location", "Rent", "Bedrooms", "Bathrooms", "Square Feet", "Link", "Adr",
    "Utilities", "Estimated Profit", "Estimated Earnings", "Yearly Rent Cost", "Occupancy Rate",
    "Zillow Property Status",
]
FILTER_DATE_FORMAT = '%B %d, %Y'
BATCH_SEQUENCE_KEY = 'rental-batch-sequence'


class _EchoBuffer:
    """File-like sink that hands each csv.writer row straight back for streaming."""

    def write(self, value):
        return value


def _csv_safe(value):
    # Spreadsheet apps execute cells that start with these characters as formulas.
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def _next_batch_id():
    """Reserve a batch number atomically.

    Rows are only written once the Celery task runs, so reading Max(batch_id) gave two uploads
    made in quick succession the same batch. The counter lives in the shared (Redis) cache and
    is re-seeded from the database if the key is ever evicted.
    """
    if cache.get(BATCH_SEQUENCE_KEY) is None:
        cache.add(BATCH_SEQUENCE_KEY, RentalProperty.objects.aggregate(Max('batch_id'))['batch_id__max'] or 0,
                  timeout=None)
    return cache.incr(BATCH_SEQUENCE_KEY)


def _parse_filter_date(value, field):
    if not value:
        return None
    try:
        return datetime.strptime(value, FILTER_DATE_FORMAT).date()
    except (TypeError, ValueError):
        raise ValidationError({field: 'Use "Month day, year" (e.g., December 3, 2024).'})


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
        return max(1, min(page_size, self.max_page_size))


class RentalPropertyViewSet(viewsets.ModelViewSet):
    queryset = RentalProperty.objects.all().order_by('-created_at')
    permission_classes = [IsAuthenticated, IsSpecificUserType, IsAdminOrOwnData]
    serializer_class = RentalPropertySerializer
    pagination_class = RentalPropertyPagination

    def get_queryset(self):
        rows = RentalProperty.objects.all().order_by('-created_at')
        return rows if self.request.user.is_staff else rows.filter(user_id=self.request.user.pk)

    def perform_create(self, serializer):
        serializer.save(user_id=self.request.user.pk)

    @action(detail=False, methods=['post'], url_path='upload-properties')
    def upload_rental_properties(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"success": False, "message": "File not found"}, status=status.HTTP_400_BAD_REQUEST)

        if not validate_file_type(file):
            return Response({"success": False, "message": "Invalid file type; upload .csv or .xlsx"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            df = file_to_df(file)
        except (ValueError, pd.errors.ParserError, zipfile.BadZipFile, InvalidFileException):
            return Response({"success": False, "message": "File could not be read as CSV or XLSX"},
                            status=status.HTTP_400_BAD_REQUEST)
        if df.empty:
            return Response({"success": False, "message": "File contains no data"}, status=status.HTTP_400_BAD_REQUEST)

        missing_cols = validate_df(df)
        if missing_cols:
            return Response(
                {"success": False, "message": f"Missing columns: {', '.join(sorted(missing_cols))}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        normalize_column(df, "Ba")
        normalize_column(df, "Br")
        normalize_column(df, "Sq. ft.")
        df["Price"] = df["Price"].apply(clean_price)

        new_batch_id = _next_batch_id()
        df = normalize_df(df)
        context = {
            'user': request.user.id,
            'new_batch_id': new_batch_id
        }

        task = process_rental_properties_task.delay(df.to_json(orient='records'), context)
        cache.set('rental-task-owner:' + task.id, request.user.pk, timeout=86400)

        return Response(
            {"success": True, "message": f"Batch {new_batch_id} processing started", "task_id": task.id},
            status=status.HTTP_202_ACCEPTED
        )

    @action(detail=False, methods=['get'], url_path='task-result')
    def get_task_result(self, request):
        task_id = request.query_params.get("task_id")
        if not task_id:
            return Response({"success": False, "message": "Task ID is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not request.user.is_staff and cache.get('rental-task-owner:' + task_id) != request.user.pk:
            raise PermissionDenied('Task is not owned by this account.')
        task_result = AsyncResult(task_id)
        if task_result.state == "PENDING":
            return Response({"success": False, "message": "Task is still pending"}, status=status.HTTP_202_ACCEPTED)
        elif task_result.state == "FAILURE":
            return Response(
                {"success": False, "message": "Task failed", "error": str(task_result.result)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        elif task_result.state == "SUCCESS":
            return Response(
                {"success": True, "message": "Task completed", "result": task_result.result},
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {"success": True, "message": f"Task is {task_result.state}", "result": task_result.result},
                status=status.HTTP_200_OK
            )

    @action(detail=False, methods=['get'], url_path='task-progress')
    def task_progress(self, request):
        task_id = request.query_params.get("task_id")
        if not task_id:
            return Response({"success": False, "message": "Task ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch task result using task_id
        if not request.user.is_staff and cache.get('rental-task-owner:' + task_id) != request.user.pk:
            raise PermissionDenied('Task is not owned by this account.')
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
        rental_properties = self.get_queryset().order_by('-created_at')

        # Paginate the results
        paginator = RentalPropertyPagination()
        paginated_properties = paginator.paginate_queryset(rental_properties, request)

        # Serialize the results
        serializer = self.get_serializer(paginated_properties, many=True)

        # Return paginated response
        return paginator.get_paginated_response(serializer.data)

    def _filter_properties(self, params):
        """Apply the shared profit/status/batch/date filters used by the list and CSV export."""
        query = Q()
        for param, lookup in (
            ("min_profit", "monthly_estimated_profit__gte"),
            ("max_profit", "monthly_estimated_profit__lte"),
            ("batch_id", "batch_id"),
        ):
            value = params.get(param)
            if value is None or value == "":
                continue
            try:
                query &= Q(**{lookup: Decimal(str(value))})
            except InvalidOperation:
                raise ValidationError({param: "Must be a number."})
        if params.get("status"):
            query &= Q(property_status=params["status"])
        start_date = _parse_filter_date(params.get("start_date"), "start_date")
        if start_date:
            query &= Q(created_at__date__gte=start_date)
        end_date = _parse_filter_date(params.get("end_date"), "end_date")
        if end_date:
            query &= Q(created_at__date__lte=end_date)
        return self.get_queryset().filter(query).order_by('-created_at')

    @action(detail=False, methods=['post'], url_path='filtered-list')
    def filtered_list(self, request):
        rental_properties = self._filter_properties(request.data)
        all_batch_ids = sorted(set(rental_properties.values_list('batch_id', flat=True)))

        paginator = RentalPropertyPagination()
        paginated_properties = paginator.paginate_queryset(rental_properties, request)
        serializer = self.get_serializer(paginated_properties, many=True)
        return paginator.get_paginated_response({
            'all_batch_ids': all_batch_ids,
            'properties': serializer.data,
        })

    @action(detail=False, methods=['get'], url_path='download-csv')
    def download_csv(self, request):
        rental_properties = self._filter_properties(request.query_params)

        def generate_csv():
            buffer = _EchoBuffer()
            writer = csv.writer(buffer)
            yield writer.writerow(CSV_HEADER)
            for prop in rental_properties.iterator():
                yield writer.writerow([
                    prop.created_at.strftime('%B %d, %Y') if prop.created_at else "",
                    prop.batch_id,
                    _csv_safe(prop.location),
                    prop.rent,
                    prop.no_of_bedrooms,
                    prop.no_of_bathrooms,
                    prop.square_feet,
                    _csv_safe(prop.property_zillow_link),
                    prop.adr,
                    prop.utilities,
                    prop.monthly_estimated_profit,
                    prop.yearly_projected_revenue,
                    prop.yearly_rent_cost_util,
                    prop.occupancy_rate,
                    prop.property_status,
                ])

        response = StreamingHttpResponse(generate_csv(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="rental_properties.csv"'
        return response
