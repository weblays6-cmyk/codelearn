from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import redirect

from .session_security import reserve_login


class BlogAccountAdapter(DefaultAccountAdapter):
    def login(self, request, user):
        login_method = request.session.get('_vgh_login_method', 'Google')
        result = reserve_login(request, user, login_method)
        if result.status == 'sessions':
            raise ImmediateHttpResponse(redirect('blog:manage_active_sessions'))
        if result.status == 'allowance':
            request.session['_vgh_login_error'] = (
                'Your total successful login allowance has been exhausted.'
            )
            request.session.modified = True
            raise ImmediateHttpResponse(redirect('blog:login'))
        super().login(request, user)


class BlogSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        request.session['_vgh_login_method'] = 'Google'
        request.session.modified = True
