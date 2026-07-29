import json
import logging

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.exceptions import ValidationError
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

logger = logging.getLogger(__name__)


def _user_conversations(request):
    return Conversation.objects.filter(
        user=request.user
    )


def _get_bank(bank_code: str | None):
    """
    Resolve the code sent by the Angular bank selector.

    The selector displays the real name but intentionally sends the stable
    internal code used by the existing foreign keys and payload files.
    """

    if not bank_code:
        return None

    from organizations.models import Bank

    bank = Bank.objects.filter(
        code=bank_code
    ).first()

    if bank is None:
        raise ValidationError(
            {
                "bank_code": (
                    f"No bank exists with code "
                    f"'{bank_code}'."
                )
            }
        )

    return bank


def resolve_conversation(
    request,
    data,
) -> Conversation:
    """
    Resolve or create a conversation and apply the selected bank scope.

    For an older conversation that was accidentally created without a bank,
    the bank sent by the current request is attached automatically. A
    conversation that is already scoped cannot silently switch banks.
    """

    conversation_id = data.get(
        "conversation_id"
    )
    requested_bank = _get_bank(
        data.get("bank_code")
    )

    if conversation_id:
        conversation = _user_conversations(
            request
        ).get(id=conversation_id)

        if requested_bank is not None:
            if conversation.bank_id is None:
                conversation.bank = (
                    requested_bank
                )
                conversation.save(
                    update_fields=[
                        "bank",
                        "updated_at",
                    ]
                )
            elif (
                conversation.bank_id
                != requested_bank.pk
            ):
                raise ValidationError(
                    {
                        "bank_code": (
                            "This conversation is already "
                            f"scoped to "
                            f"'{conversation.bank.name}'. "
                            "Start a new chat to use another "
                            "bank."
                        )
                    }
                )

        return conversation

    return Conversation.objects.create(
        user=request.user,
        bank=requested_bank,
        title=data["message"][:60],
    )


class ChatView(APIView):
    """Normal non-streaming fallback endpoint."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(
            data=request.data
        )
        serializer.is_valid(
            raise_exception=True
        )
        data = serializer.validated_data

        conversation = resolve_conversation(
            request,
            data,
        )
        assistant_message = run_turn(
            conversation,
            data["message"],
        )

        return Response(
            {
                "conversation_id": str(
                    conversation.id
                ),
                "message": MessageSerializer(
                    assistant_message
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class ChatStreamView(APIView):
    """
    Stream Azure assistant events to Angular.

    The conversation has already been assigned the selected bank before the
    generator builds the system prompt.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(
            data=request.data
        )
        serializer.is_valid(
            raise_exception=True
        )
        data = serializer.validated_data

        conversation = resolve_conversation(
            request,
            data,
        )

        def event_stream():
            yield ": connected\n\n"

            try:
                for event in run_turn_streamed(
                    conversation,
                    data["message"],
                ):
                    yield (
                        "data: "
                        + json.dumps(
                            event,
                            default=str,
                        )
                        + "\n\n"
                    )
            except Exception:
                logger.exception(
                    "Assistant SSE response failed"
                )
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "error",
                            "message": (
                                "The assistant stream "
                                "failed."
                            ),
                        }
                    )
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


class ConversationListView(
    ListAPIView
):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer

    def get_queryset(self):
        return _user_conversations(
            self.request
        )


class ConversationDetailView(
    RetrieveAPIView
):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer
    lookup_field = "id"

    def get_queryset(self):
        return _user_conversations(
            self.request
        )
