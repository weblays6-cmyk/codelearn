from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from .models import UserProfile, UserSession
from .services.course_progress import has_active_premium


def device_label_from_user_agent(user_agent):
    user_agent = (user_agent or '').lower()
    if 'ipad' in user_agent or 'tablet' in user_agent:
        device = 'Tablet'
    elif 'mobile' in user_agent or 'iphone' in user_agent or 'android' in user_agent:
        device = 'Mobile'
    elif 'windows' in user_agent:
        device = 'Windows computer'
    elif 'macintosh' in user_agent or 'mac os' in user_agent:
        device = 'Mac'
    elif 'linux' in user_agent:
        device = 'Linux computer'
    else:
        device = 'Unknown device'

    if 'edg/' in user_agent:
        browser = 'Edge'
    elif 'firefox/' in user_agent:
        browser = 'Firefox'
    elif 'chrome/' in user_agent and 'edg/' not in user_agent:
        browser = 'Chrome'
    elif 'safari/' in user_agent and 'chrome/' not in user_agent:
        browser = 'Safari'
    else:
        browser = ''
    return f'{device} · {browser}' if browser else device


def device_limit_for(user):
    profile = UserProfile.objects.get_or_create(user=user)[0]
    if has_active_premium(user):
        return max(1, int(getattr(settings, 'MAX_DEVICES', 3)))
    return 1


def cleanup_expired_device_sessions():
    expired_keys = Session.objects.filter(
        expire_date__lte=timezone.now(),
    ).values('session_key')
    UserSession.objects.filter(session_key__in=expired_keys).delete()


def enforce_device_limit(user):
    active_devices = list(
        UserSession.objects.filter(user=user, is_active=True)
        .order_by('created_at', 'pk')
    )
    excess = active_devices[:-device_limit_for(user)]
    if not excess:
        return
    revoked_keys = [item.session_key for item in excess]
    UserSession.objects.filter(pk__in=[item.pk for item in excess]).update(
        is_active=False,
    )
    Session.objects.filter(session_key__in=revoked_keys).delete()


def register_device_session(request, user):
    session_key = getattr(request.session, 'session_key', None)
    if not session_key:
        return None

    now = timezone.now()
    with transaction.atomic():
        cleanup_expired_device_sessions()
        device, created = UserSession.objects.get_or_create(
            session_key=session_key,
            defaults={
                'user': user,
                'device_label': device_label_from_user_agent(
                    request.META.get('HTTP_USER_AGENT', '')
                ),
                'ip': request.META.get('REMOTE_ADDR') or None,
                'last_seen': now,
            },
        )
        if not created and device.user_id != user.pk:
            device.user = user
            device.device_label = device_label_from_user_agent(
                request.META.get('HTTP_USER_AGENT', '')
            )
            device.ip = request.META.get('REMOTE_ADDR') or None
            device.created_at = now
            device.last_seen = now
            device.is_active = True
            device.save(update_fields=(
                'user', 'device_label', 'ip', 'created_at', 'last_seen', 'is_active',
            ))
        else:
            UserSession.objects.filter(pk=device.pk).update(
                device_label=device_label_from_user_agent(
                    request.META.get('HTTP_USER_AGENT', '')
                ),
                ip=request.META.get('REMOTE_ADDR') or None,
                last_seen=now,
                is_active=True,
            )

        enforce_device_limit(user)
    return device


def touch_device_session(device):
    now = timezone.now()
    if device.last_seen <= now - timedelta(minutes=5):
        UserSession.objects.filter(
            pk=device.pk,
            is_active=True,
            last_seen=device.last_seen,
        ).update(last_seen=now)
