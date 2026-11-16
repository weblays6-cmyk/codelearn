import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Q

from .models import Message


logger = logging.getLogger(__name__)


def get_unread_message_count(user_id):
    return Message.objects.filter(
        Q(conversation__project_owner_id=user_id)
        | Q(conversation__participant_id=user_id),
        is_read=False,
    ).exclude(
        sender_id=user_id,
    ).count()


def broadcast_message_count_update(user_id):
    try:
        async_to_sync(get_channel_layer().group_send)(
            f'message_notifications_{user_id}',
            {
                'type': 'message_count.updated',
            },
        )
    except Exception:
        logger.exception(
            'Could not broadcast unread message count for user %s.',
            user_id,
        )


def broadcast_chat_message_popup(
    recipient_id,
    conversation_id,
    sender_name,
    preview,
    conversation_url,
):
    try:
        async_to_sync(get_channel_layer().group_send)(
            f'message_notifications_{recipient_id}',
            {
                'type': 'chat.message_popup',
                'conversation_id': conversation_id,
                'sender_name': sender_name,
                'preview': preview[:180],
                'url': conversation_url,
            },
        )
    except Exception:
        logger.exception(
            'Could not broadcast chat message popup for user %s.',
            recipient_id,
        )
