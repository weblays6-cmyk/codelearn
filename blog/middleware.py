from django.shortcuts import redirect

from .models import UserProfile
from .session_security import enforce_active_session


class ActiveSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            response = enforce_active_session(request, request.user)
            if response is not None:
                return response
        return self.get_response(request)


class AccountLifecycleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            profile = UserProfile.objects.filter(user_id=user.pk).only(
                'is_deactivated',
                'scheduled_deletion_at',
            ).first()
            if profile and (
                profile.is_deactivated or profile.scheduled_deletion_at
            ):
                allowed_prefixes = (
                    '/account/recovery/',
                    '/accounts/',
                    '/login/',
                    '/logout/',
                    '/static/',
                    '/media/',
                )
                if not request.path_info.startswith(allowed_prefixes):
                    return redirect('blog:account_recovery')

        return self.get_response(request)
