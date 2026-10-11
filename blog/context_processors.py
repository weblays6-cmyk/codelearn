from django.conf import settings

from .message_notifications import get_unread_message_count


def site_name(request):
    return {
        "SITE_NAME": settings.SITE_NAME
    }


def unread_message_count(request):

    if not request.user.is_authenticated:
        return {
            "UNREAD_MESSAGE_COUNT": 0
        }

    return {
        "UNREAD_MESSAGE_COUNT": get_unread_message_count(request.user.id)
    }