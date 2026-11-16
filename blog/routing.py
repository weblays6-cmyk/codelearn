from django.urls import path

from .consumers import ConversationConsumer, MessageNotificationsConsumer


websocket_urlpatterns = [
    path(
        'ws/messages/notifications/',
        MessageNotificationsConsumer.as_asgi(),
    ),
    path(
        'ws/messages/<int:conversation_id>/',
        ConversationConsumer.as_asgi(),
    ),
]
