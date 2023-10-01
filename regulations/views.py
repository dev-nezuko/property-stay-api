from datetime import datetime, timedelta, timezone
import re
import openai
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .permissions import IsSpecificUserType, IsAdminOrOwnData
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from django.conf import settings
from .models import Regulations
from .serializers import GPTChatSerializer, RegulationsSerializer
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action

class RegulationsViewSet(viewsets.ModelViewSet):
    queryset = Regulations.objects.all().order_by('-created_at')
    filter_backends = [SearchFilter, OrderingFilter, DjangoFilterBackend]
    search_fields = ['search', 'status']
    filterset_fields = ['search', 'status']
    permission_classes = [IsAuthenticated, IsSpecificUserType , IsAdminOrOwnData]
    pagination_class = PageNumberPagination
    serializer_class = RegulationsSerializer

    def get_queryset(self):
        """
        Restrict non-admin users to only their data and apply ordering.
        """
        if self.request.user.is_staff:
            return Regulations.objects.all().order_by("-created_at")  # Apply ordering here
        return Regulations.objects.filter(user=self.request.user).order_by("-created_at")  # Apply ordering for user data


    def perform_create(self, serializer):
        user = self.request.user
        regulation = serializer.save(user=user)
        gpt_analysis = self._analyze_location_with_gpt(regulation)

        # Update the regulation instance with GPT results
        regulation.status = gpt_analysis['status']
        regulation.gpt_response = gpt_analysis
        regulation.save()

    def _analyze_location_with_gpt(self, regulation):
        """
        Analyze the given address, city, and area using GPT-4 and return the status and response.
        """
        # Prepare the system message and user input
        system_message = """
                This GPT acts as a knowledgeable consultant specializing in short-term rental (STR) laws, providing users with concise and accurate information, advice, and strategies related to the legality of short-term rentals in various areas.
                Each response begins with a clear status update of the STR legality in the specific area: 
                
                'SHORT TERM RENTAL ALLOWED,' 'SHORT TERM RENTAL ALLOWED WITH RESTRICTIONS,' or 'SHORT TERM RENTAL NOT ALLOWED.'

                After this, the GPT offers bullet-point summaries of the relevant regulations, ensuring that users can quickly grasp the key points.
                The information is thoroughly sourced from official government websites, and all URLs in the response will be formatted using **Markdown syntax** to ensure they are **100% clickable**, like this: [Click here](http://example.com).
                Each clickable link will also include the source site to make it clear where the information is coming from, ensuring full transparency and accuracy.
                If STRs are banned or restricted, the GPT actively researches and highlights any potential loopholes, alternative permits, reclassification strategies, or other legal workarounds that could enable operation in the area.
                This includes exploring options like unincorporated areas, alternate zoning classifications, or non-primary residence allowances.
                The GPT will even suggest searches or perform extra research using real-time tools to uncover additional ways to operate a short-term rental legally.
                It also explains how local rules differ in unincorporated areas or offers advice on how to apply for permits or operate within a permissible framework by reclassifying the property.
                The GPT will reference specific codes, ordinances, and regulations by citing exact clauses and sections, such as 'LUC 20.20.800' or other relevant statutes, ensuring the accuracy of the legal advice provided.
                In cases where short-term rentals are subject to zoning regulations, the GPT assists users in understanding and addressing zoning issues and permits.
                In cases where specific residency requirements are in place, the GPT will clarify in exact terms whether the law applies to property owners, authorized agents, tenants, or other representatives.
                For example, in areas like Kirkland, Washington, where specific rules apply, it will state that the property owner or an authorized agent must occupy the property for a minimum of 245 days per year to qualify the residence for short-term rentals.
                Responses are informative and thorough, providing helpful resources and citations with clickable links to ensure users have access to the most relevant and accurate information.
                Importantly, the GPT clarifies whether short-term rental laws apply to owners, renters, agents, or representatives, and offers strategies for compliance or legal workarounds.

                Please ensure the status is clearly mentioned in the response along with a summary of your findings.

                """
        user_input = f"""
        Analyze the legality of short-term rentals for the following details:
        - Search: {regulation.search}
        """

        try:
            # Call GPT-4 API
            openai.api_key = settings.OPENAI_API_KEY
            response = openai.ChatCompletion.create(
                model="gpt-4",
                temperature=0.7,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_input}
                ]
            )

            gpt_content = response['choices'][0]['message']['content'].strip()
            created_time = response.get('created')

            # Ensure created_time is a string in ISO 8601 format
            if isinstance(created_time, (int, float)):
                created_time = datetime.fromtimestamp(created_time, tz=timezone.utc).isoformat()
            
            timestamp = datetime.now(timezone.utc).isoformat()

            if re.search(r'\bSHORT TERM RENTAL ALLOWED WITH RESTRICTIONS\b', gpt_content, re.IGNORECASE):
                status = 'STR Allowed with Restrictions'
            elif re.search(r'\bSHORT TERM RENTAL ALLOWED\b', gpt_content, re.IGNORECASE):
                status = 'STR Allowed'
            elif re.search(r'\bSHORT TERM RENTAL NOT ALLOWED\b', gpt_content, re.IGNORECASE):
                status = 'STR Not Allowed'
            else:
                status = 'pending'

            return {
                'status': status,
                'message': gpt_content,
                'created_time': timestamp
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }
    
    @action(detail=True, methods=['post'], url_path='chat')
    def chat_with_gpt(self, request, pk=None):
        """
        Chat with GPT regarding a specific regulation.
        """
        serializer = GPTChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        regulation_id = serializer.validated_data.get('regulation_id')
        user_message = serializer.validated_data.get('message')

        regulation = get_object_or_404(Regulations, id=regulation_id)
    
        # Fetch the summary from the regulation's GPT response
        gpt_response_data = regulation.gpt_response if regulation.gpt_response else {}
        summary = gpt_response_data.get('message', 'No summary available.')

        # Prepare the system message with context
        system_message = f"""
        This GPT acts as a knowledgeable consultant specializing in short-term rental (STR) laws, providing users with concise and accurate information, advice, and strategies related to the legality of short-term rentals in various areas.

        Key responsibilities include:
        - Provide **clear status updates** on the legality of short-term rentals (STR) in the given area.
        - Offer **bullet-point summaries** of relevant regulations and guidelines for quick comprehension.
        - Source information **from official government websites**, ensuring accuracy and transparency.
        - Format all URLs using **Markdown syntax** to make them **clickable and informative**.
        - Highlight **loopholes, alternative permits, or legal workarounds** for areas where STRs are restricted or banned.
        - Explore **unincorporated areas** or **reclassification strategies** for potential legal operation.
        - Reference specific **codes, ordinances, and statutes** (e.g., "LUC 20.20.800") in responses for legal accuracy.
        - Assist users in understanding **zoning regulations, permits**, and **residency requirements**.
        - Provide guidance on compliance strategies, including **applying for permits** or **reclassifying properties**.
        - Offer **strategic advice** on how local rules apply to **property owners, renters, or agents**.
        - Suggest additional resources, searches, or research strategies for **legal compliance**.
        - Clarify the specific residency or occupancy requirements necessary to **qualify a property** for STR.
        
        Here’s a summary of previous analysis:
        {summary}

        Please assist the user with further queries regarding the regulation. Provide relevant responses based on the summary and chat history.
        """
        
        # Initialize chat history
        chat_history = regulation.chat_history or []
        
        # Add user's message to chat history
        user_message_entry = {
            'role': 'user',
            'content': user_message,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        chat_history.append(user_message_entry)

        try:
            # Generate GPT response
            openai.api_key = settings.OPENAI_API_KEY
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {'role': 'system', 'content': system_message},
                    *chat_history
                ]
            )
            gpt_response = response['choices'][0]['message']['content']

            # Append GPT's response to the chat history
            gpt_response_entry ={
                'role': 'assistant',
                'content': gpt_response,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            chat_history.append(gpt_response_entry)
            regulation.chat_history = chat_history
            regulation.save()

            return Response({
                'response': gpt_response,
                'chat_history': chat_history,
                'summary': summary
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'], url_path='get-chat-history')
    def get_chat_history(self, request, pk=None):
        """
        Retrieve chat history for a specific regulation.
        """
        regulation = get_object_or_404(Regulations, id=pk)

        gpt_response_data = regulation.gpt_response if regulation.gpt_response else {}
        # Ensure gpt_response_data is a dictionary before accessing its keys
        if isinstance(gpt_response_data, dict):
            gpt_response = {
                'message': gpt_response_data.get('message'),
                'status': gpt_response_data.get('status'),
                'timestamp': gpt_response_data.get('created_time')
            }
        else:
            gpt_response = {
                'message': None,
                'status': None,
                'timestamp': None
            }

        chat_history = regulation.chat_history or []

        response_data = {
            'gpt_response': gpt_response,
            'chat_history': chat_history,
        }
        return Response(response_data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_path='search')
    def search(self, request):
        """
        Search regulations by address, city, or area, with optional filters for date range and status.
        """
        # Fetch query parameters
        query = request.query_params.get('query')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        status_value = request.query_params.get('status')

        # Initial queryset
        regulations = Regulations.objects.all()

        # Filter by search
        if query:
          regulations = regulations.filter(search__icontains=query)


        # Filter by created_at for date range
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                regulations = regulations.filter(created_at__gte=start_date)
            except ValueError:
                return Response({'detail': 'Invalid start date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                end_date = end_date + timedelta(days=1)  # Include the entire end day
                regulations = regulations.filter(created_at__lte=end_date)
            except ValueError:
                return Response({'detail': 'Invalid end date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            end_date = datetime.now().date()


        # Filter by status if provided
        if status_value:
            regulations = regulations.filter(status=status_value)

        # Apply ordering by creation date
        regulations = regulations.order_by('-created_at')

        # Apply pagination
        page = self.paginate_queryset(regulations)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(regulations, many=True)
        return Response(serializer.data if regulations.exists() else {'detail': 'No regulations found.'}, status=status.HTTP_200_OK)