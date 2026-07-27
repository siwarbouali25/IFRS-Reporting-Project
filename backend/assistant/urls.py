from django.urls import path

from .views import (
    ChatStreamView,
    ChatView,
    ConversationDetailView,
    ConversationListView,
)

urlpatterns = [
    path("assistant/chat/", ChatView.as_view(), name="assistant-chat"),
    path("assistant/chat/stream/", ChatStreamView.as_view(), name="assistant-chat-stream"),
    path("assistant/conversations/", ConversationListView.as_view(), name="assistant-conversations"),
    path("assistant/conversations/<uuid:id>/", ConversationDetailView.as_view(), name="assistant-conversation-detail"),
]
