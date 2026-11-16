import logging
import re

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core import context as allauth_context
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.contrib.auth import get_user_model


logger = logging.getLogger(__name__)


class VGrowHubAccountAdapter(DefaultAccountAdapter):
    def send_mail(self, template_prefix, email, context):
        try:
            super().send_mail(template_prefix, email, context)
        except Exception:
            logger.exception(
                'vGrowHub account email delivery failed for %s.',
                template_prefix,
            )
            request = getattr(allauth_context, 'request', None)
            if request is not None:
                messages.error(
                    request,
                    "We couldn't send the email. Please try again later.",
                )


class VGrowHubSocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        email = data.get('email') or sociallogin.account.extra_data.get('email', '')
        if email:
            user.email = email

        username_field = get_user_model().USERNAME_FIELD
        if not getattr(user, username_field, ''):
            prefix = email.partition('@')[0] if email else ''
            base = re.sub(r'[^A-Za-z0-9._+-]', '', prefix).lower() or 'user'
            max_length = get_user_model()._meta.get_field(username_field).max_length or 150
            base = base[:max_length]
            manager = get_user_model()._default_manager

            candidate = base
            suffix_number = 2
            while manager.filter(**{f'{username_field}__iexact': candidate}).exists():
                suffix = str(suffix_number)
                candidate = f'{base[:max_length - len(suffix)]}{suffix}'
                suffix_number += 1

            setattr(user, username_field, candidate)

        return user
