import json

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.generics import (
    ListAPIView,
    RetrieveAPIView,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .agent import run_turn
from .models import Conversation
from .serializers import (
    ChatRequestSerializer,
    ConversationSerializer,
    MessageSerializer,
)
from .streaming import run_turn_streamed


def _user_conversations(request):
    return Conversation.objects.filter(user=request.user)


def resolve_conversation(request, data) -> Conversation:
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
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        conversation = resolve_conversation(request, data)
        assistant_msg = run_turn(
            conversation,
            data["message"],
        )

        return Response(
            {
                "conversation_id": str(conversation.id),
                "message": MessageSerializer(
                    assistant_msg
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class ChatStreamView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        conversation = resolve_conversation(request, data)

        def event_stream():
            # Open the SSE response immediately. Comment frames are valid SSE
            # and are ignored by the Angular parser.
            yield ": connected\n\n"

            try:
                for event in run_turn_streamed(
                    conversation,
                    data["message"],
                ):
                    yield (
                        "data: "
                        + json.dumps(event, default=str)
                        + "\n\n"
                    )
            except Exception:
                error_event = {
                    "type": "error",
                    "message": "The assistant stream failed.",
                }
                yield (
                    "data: "
                    + json.dumps(error_event)
                    + "\n\n"
                )

        response = StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = (
            "no-cache, no-transform"
        )
        response["X-Accel-Buffering"] = "no"
        response["Content-Encoding"] = "identity"
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
