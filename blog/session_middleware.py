from datetime import timedelta

from django.contrib.auth import logout
from django.contrib.sessions.models import Session
from django.shortcuts import redirect
from django.utils import timezone
from django.urls import reverse
from django.conf import settings
from django.http import JsonResponse

from .device_sessions import (
    cleanup_expired_device_sessions,
    register_device_session,
    touch_device_session,
)
from .models import UserSession


class DeviceSessionMiddleware:
    cleanup_checked_at = None

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        now = timezone.now()
        if (
            self.cleanup_checked_at is None
            or now - self.cleanup_checked_at >= timedelta(minutes=5)
        ):
            cleanup_expired_device_sessions()
            self.cleanup_checked_at = now

        session_key = (
            request.session.session_key
            or request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        )
        device = (
            UserSession.objects.filter(session_key=session_key).first()
            if session_key
            else None
        )
        if device and not device.is_active:
            Session.objects.filter(session_key=session_key).delete()
            device.delete()
            logout(request)
            if request.path == '/api/live-counts/':
                return JsonResponse({'error': 'session_revoked'}, status=401)
            return redirect(f'{reverse("blog:login")}?device_signed_out=1')

        if request.user.is_authenticated:
            if device is None:
                device = register_device_session(request, request.user)
            elif device.is_active:
                touch_device_session(device)

        return self.get_response(request)
