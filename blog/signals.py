import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from .gmail_service import build_site_url, send_gmail
from .models import Notification, UserProfile
from .session_security import (
    register_successful_login,
    remove_logged_out_session,
)

logger = logging.getLogger(__name__)


user_logged_in.connect(
    register_successful_login,
    dispatch_uid='blog.register_successful_login_session',
)
user_logged_out.connect(
    remove_logged_out_session,
    dispatch_uid='blog.remove_logged_out_session',
)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        display_name = instance.get_full_name().strip() or instance.username
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                'display_name': display_name,
                'onboarding_completed': False,
            },
        )


def send_notification_email(notification_id):
    try:
        notification = Notification.objects.select_related(
            'recipient',
            'sender',
        ).get(pk=notification_id)
    except Notification.DoesNotExist:
        logger.exception(
            'Could not load notification %s for email delivery.',
            notification_id,
        )
        return

    recipient = notification.recipient
    if not recipient.email:
        logger.info(
            'Notification email skipped for user %s because no email is configured.',
            recipient.pk,
        )
        return

    sender_name = (
        notification.sender.profile_data.display_name
        or notification.sender.get_full_name()
        or notification.sender.username
    )
    notification_url = build_site_url(reverse('blog:notifications'))
    try:
        send_gmail(
            recipient.email,
            f'New {notification.get_notification_type_display()} on vGrowHub',
            f"""Hello @{recipient.username},

{sender_name} sent you a notification:

{notification.message}

View your notifications: {notification_url}

Regards,
vGrowHub Team
""",
        )
    except Exception:
        logger.exception(
            'Notification email delivery failed for notification %s and user %s.',
            notification.pk,
            recipient.pk,
        )


@receiver(post_save, sender=Notification)
def email_new_notification(sender, instance, created, **kwargs):
    if created:
        transaction.on_commit(
            lambda notification_id=instance.pk: send_notification_email(
                notification_id,
            ),
        )


@receiver(
    user_logged_in,
    dispatch_uid='blog.send_vgrowhub_login_notification',
)
def send_login_notification(sender, request, user, **kwargs):
    if getattr(request, '_vgh_login_notification_sent', False):
        return
    request._vgh_login_notification_sent = True

    login_method = request.session.pop('_vgh_login_method', None)
    if not login_method:
        login_method = (
            'Google'
            if '/google/' in request.path.lower()
            else 'Account'
        )
    if not user.email:
        logger.info(
            'Login notification skipped for user %s because no email is configured.',
            user.pk,
        )
        return

    try:
        send_gmail(
            user.email,
            'New login to your vGrowHub account',
            f"""Hello @{user.username},

Your vGrowHub account was successfully logged in.

Username: @{user.username}
Login method: {login_method}
Login time: {timezone.localtime().strftime("%B %d, %Y at %I:%M %p %Z")}

If this was not you, please secure your account.

Regards,
vGrowHub Team
""",
        )
    except Exception:
        logger.exception(
            'vGrowHub login alert email delivery failed for user %s.',
            user.pk,
        )
