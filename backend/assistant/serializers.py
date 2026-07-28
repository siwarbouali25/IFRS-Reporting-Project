from rest_framework import serializers

from .models import Conversation, Message


class MessageSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = Message
        fields = [
            "id",
            "role",
            "content",
            "citations",
            "model_used",
            "is_fallback",
            "created_at",
        ]
        read_only_fields = fields


class ConversationSerializer(
    serializers.ModelSerializer
):
    messages = MessageSerializer(
        many=True,
        read_only=True,
    )
    bank_code = serializers.CharField(
        source="bank.code",
        read_only=True,
    )
    bank_name = serializers.CharField(
        source="bank.name",
        read_only=True,
    )

    class Meta:
        model = Conversation
        fields = [
            "id",
            "title",
            "bank_code",
            "bank_name",
            "created_at",
            "updated_at",
            "messages",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "messages",
            "bank_code",
            "bank_name",
        ]


class ChatRequestSerializer(
    serializers.Serializer
):
    conversation_id = serializers.UUIDField(
        required=False
    )
    # Kept as bank_code for API compatibility with the current Angular page.
    # The value remains the internal code, while all visible labels use names.
    bank_code = serializers.CharField(
        required=False,
        allow_blank=True,
    )
    message = serializers.CharField()
