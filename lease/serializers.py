# serializers.py
from rest_framework import serializers
from .models import Lease, Document
from cloudinary.uploader import upload

class DocumentSerializer(serializers.ModelSerializer):
    lease_id = serializers.PrimaryKeyRelatedField(source='lease', read_only=True)  # To show the lease ID

    class Meta:
        model = Document
        fields = ['id', 'lease_id', 'name', 'file', 'version', 'uploaded_at' ,'status', 'gpt_response', 'chat_history']

class LeaseSerializer(serializers.ModelSerializer):
    num_of_docs = serializers.IntegerField(read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Lease
        fields = [
            'id', 'date', 'address1', 'address2', 'city', 'state', 'zip_code', 
            'status', 'num_of_docs', 'documents'
        ]

class LeaseUploadSerializer(serializers.ModelSerializer):
    documents = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = Lease
        fields = ['address1', 'address2', 'city', 'state', 'zip_code', 'status', 'documents']

    def create(self, validated_data):
        documents = validated_data.pop('documents', [])
        user = self.context['request'].user
        lease = Lease.objects.create(user=user, **validated_data)  # Associate with the user
        new_file_urls = []
        for doc in documents:
            cloudinary_file = upload(doc, use_filename=True, resource_type='raw', access_mode='public')
            new_file_urls.append(cloudinary_file['url'])
            Document.objects.create(lease=lease, file_url=cloudinary_file['url'],name=doc.name)
        return lease
    
class RevisedLeaseUploadSerializer(serializers.Serializer):
    documents = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False
    )

    def update(self, instance, validated_data):
        documents = validated_data.pop('documents', [])
        created_document_ids = []

        new_file_urls = []

        for doc in documents:
            cloudinary_file = upload(doc, use_filename=True, resource_type='raw', access_mode='public')
            new_file_urls.append(cloudinary_file['url'])
            document = Document.objects.create(lease=instance, file_url=cloudinary_file['url'],name=doc.name)
            created_document_ids.append(document.id)

        # Return the document IDs
        return created_document_ids
    
class GPTChatSerializer(serializers.Serializer):
    message = serializers.CharField(
        required=True,
        allow_blank=False,
        help_text="Enter your message or prompt to interact with the GPT model."
    )
    document_id = serializers.IntegerField(required=True)
    

