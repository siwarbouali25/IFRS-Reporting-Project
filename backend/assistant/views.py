import json

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .agent import run_turn
from .models import Conversation, Message
from .serializers import (
    ChatRequestSerializer,
    ConversationSerializer,
    MessageSerializer,
)
from .streaming import run_turn_streamed


def _user_conversations(request):
    return Conversation.objects.filter(user=request.user)


def resolve_conversation(request, data) -> Conversation:
    """Shared by both chat endpoints: fetch an existing conversation (scoped
    to the user) or create a new one, optionally bank-scoped."""
    conv_id = data.get("conversation_id")
    if conv_id:
        return _user_conversations(request).get(id=conv_id)

    bank = None
    bank_code = data.get("bank_code")
    if bank_code:
        from organizations.models import Bank

        bank = Bank.objects.filter(code=bank_code).first()

    return Conversation.objects.create(
        user=request.user,
        bank=bank,
        title=data["message"][:60],
    )


class ChatView(APIView):
    """
    POST /api/assistant/chat/
    Body: {message, conversation_id?, bank_code?}
    Non-streaming: runs one agent turn, returns the full assistant message.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        conversation = resolve_conversation(request, data)
        assistant_msg = run_turn(conversation, data["message"])

        return Response(
            {
                "conversation_id": str(conversation.id),
                "message": MessageSerializer(assistant_msg).data,
            },
            status=status.HTTP_200_OK,
        )


class ChatStreamView(APIView):
    """
    POST /api/assistant/chat/stream/
    Body: {message, conversation_id?, bank_code?}
    Streams the turn as Server-Sent Events (text/event-stream): status while
    tools run, tokens as the model writes, then citations and a done event.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        conversation = resolve_conversation(request, data)

        def event_stream():
            try:
                for event in run_turn_streamed(conversation, data["message"]):
                    yield f"data: {json.dumps(event, default=str)}\n\n"
            except Exception:  # last-resort guard so the socket closes cleanly
                yield f'data: {json.dumps({"type": "error", "message": "stream failed"})}\n\n'

        response = StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream",
        )
        # Defeat proxy/server buffering that would otherwise batch the stream.
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class ConversationListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer

    def get_queryset(self):
        return _user_conversations(self.request)


class ConversationDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer
    lookup_field = "id"

    def get_queryset(self):
        return _user_conversations(self.request)
