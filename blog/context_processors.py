from django.conf import settings
from django.db.models import Q

from .models import Message


def site_name(request):
    return {
        "SITE_NAME": settings.SITE_NAME
    }


def unread_message_count(request):

    if not request.user.is_authenticated:
        return {
            "UNREAD_MESSAGE_COUNT": 0
        }

    count = Message.objects.filter(
        Q(conversation__project_owner=request.user) |
        Q(conversation__participant=request.user),
        is_read=False
    ).exclude(
        sender=request.user
    ).count()

    return {
        "UNREAD_MESSAGE_COUNT": count
    }