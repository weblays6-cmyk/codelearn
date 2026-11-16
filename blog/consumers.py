from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db.models import Q

from .message_notifications import get_unread_message_count
from .models import Conversation, FollowRequest, UserBlock, UserProfile
from .session_security import has_active_login_session


@database_sync_to_async
def _can_access_conversation(conversation_id, user_id):
    conversation = Conversation.objects.filter(
        id=conversation_id,
    ).only(
        'id',
        'project_id',
        'project_owner_id',
        'participant_id',
    ).first()
    if not conversation or user_id not in {
        conversation.project_owner_id,
        conversation.participant_id,
    }:
        return False

    other_user_id = (
        conversation.participant_id
        if user_id == conversation.project_owner_id
        else conversation.project_owner_id
    )
    if UserProfile.objects.filter(
        user_id__in=(user_id, other_user_id),
    ).filter(
        Q(is_deactivated=True) | Q(scheduled_deletion_at__isnull=False)
    ).exists():
        return False

    if UserBlock.objects.filter(
        Q(blocker_id=user_id, blocked_id=other_user_id)
        | Q(blocker_id=other_user_id, blocked_id=user_id)
    ).exists():
        return False

    if conversation.project_id is None:
        return (
            FollowRequest.objects.filter(
                sender_id=user_id,
                receiver_id=other_user_id,
                status='ACCEPTED',
            ).exists()
            and FollowRequest.objects.filter(
                sender_id=other_user_id,
                receiver_id=user_id,
                status='ACCEPTED',
            ).exists()
        )
    return True


class ConversationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        user = self.scope['user']
        if not user.is_authenticated:
            await self.close(code=4401)
            return
        self.tracking_id = self.scope.get('session', {}).get(
            '_vgh_session_tracking_id',
        )
        if not await database_sync_to_async(has_active_login_session)(
            user.id,
            self.tracking_id,
        ):
            await self.close(code=4401)
            return
        if not await _can_access_conversation(self.conversation_id, user.id):
            await self.close(code=4403)
            return

        self.group_name = f'conversation_{self.conversation_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )

    async def chat_message(self, event):
        if not await self._authorize_event():
            return
        await self.send_json({
            'type': 'message_created',
            'message_id': event['message_id'],
        })

    async def receive_json(self, content, **kwargs):
        if not await self._authorize_event():
            return
        if (
            not isinstance(content, dict)
            or content.get('type') != 'typing'
            or not isinstance(content.get('is_typing'), bool)
        ):
            return

        user = self.scope['user']
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'chat.typing',
                'user_id': user.id,
                'is_typing': content['is_typing'],
            },
        )

    async def chat_typing(self, event):
        if not await self._authorize_event():
            return
        await self.send_json({
            'type': 'typing_status',
            'user_id': event['user_id'],
            'is_typing': event['is_typing'],
        })

    async def chat_read(self, event):
        if not await self._authorize_event():
            return
        await self.send_json({
            'type': 'read_receipt',
            'user_id': event['user_id'],
        })

    async def _authorize_event(self):
        user = self.scope['user']
        if not await database_sync_to_async(has_active_login_session)(
            user.id,
            self.tracking_id,
        ):
            await self.close(code=4401)
            return False
        if not await _can_access_conversation(self.conversation_id, user.id):
            await self.close(code=4403)
            return False
        return True


class MessageNotificationsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope['user']
        if not user.is_authenticated:
            await self.close(code=4401)
            return

        self.user_id = user.id
        self.tracking_id = self.scope.get('session', {}).get(
            '_vgh_session_tracking_id',
        )
        if not await database_sync_to_async(has_active_login_session)(
            self.user_id,
            self.tracking_id,
        ):
            await self.close(code=4401)
            return

        self.group_name = f'message_notifications_{self.user_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        count = await database_sync_to_async(get_unread_message_count)(
            self.user_id,
        )
        await self.send_json({
            'type': 'unread_count_updated',
            'count': count,
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )

    async def message_count_updated(self, event):
        if not await database_sync_to_async(has_active_login_session)(
            self.user_id,
            self.tracking_id,
        ):
            await self.close(code=4401)
            return
        count = await database_sync_to_async(get_unread_message_count)(
            self.user_id,
        )
        await self.send_json({
            'type': 'unread_count_updated',
            'count': count,
        })

    async def chat_message_popup(self, event):
        if not await database_sync_to_async(has_active_login_session)(
            self.user_id,
            self.tracking_id,
        ):
            await self.close(code=4401)
            return
        if not await _can_access_conversation(
            event['conversation_id'],
            self.user_id,
        ):
            return
        await self.send_json({
            'type': 'chat_message_popup',
            'conversation_id': event['conversation_id'],
            'sender_name': event['sender_name'],
            'preview': event['preview'],
            'url': event['url'],
        })
