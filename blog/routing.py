from django.urls import path

from .consumers import ConversationConsumer


websocket_urlpatterns = [
    path(
        'ws/messages/<int:conversation_id>/',
        ConversationConsumer.as_asgi(),
    ),
]
