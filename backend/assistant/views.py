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


def _user_conversations(request):
    return Conversation.objects.filter(user=request.user)


class ChatView(APIView):
    """
    POST /api/assistant/chat/
    Body: {message, conversation_id?, bank_code?}
    Creates a conversation if none given, runs one agent turn, returns the
    assistant message with citations.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        conversation = self._resolve_conversation(request, data)
        assistant_msg = run_turn(conversation, data["message"])

        return Response(
            {
                "conversation_id": str(conversation.id),
                "message": MessageSerializer(assistant_msg).data,
            },
            status=status.HTTP_200_OK,
        )

    def _resolve_conversation(self, request, data) -> Conversation:
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
