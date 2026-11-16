import importlib
from datetime import timedelta
from types import SimpleNamespace

from allauth.core.exceptions import ImmediateHttpResponse
from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import AnonymousUser, User
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from .admin import UserLoginSessionAdmin
from .adapters import BlogAccountAdapter, BlogSocialAccountAdapter
from .models import PendingUserLogin, UserLoginSession
from .session_security import session_tracking_digest


class ConcurrentLoginLimitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'session-user',
            email='session-user@example.test',
            password='StrongPassword!123',
        )
        self.profile = self.user.profile_data
        self.profile.max_active_sessions = 1
        self.profile.save(update_fields=('max_active_sessions',))

    def login(self, client):
        return client.post(
            reverse('blog:login'),
            {'username': self.user.username, 'password': 'StrongPassword!123'},
        )

    def test_password_login_requires_selection_at_limit_and_replacement_revokes_old(self):
        original_browser = Client()
        replacement_browser = Client()

        response = self.login(original_browser)
        self.assertRedirects(
            response,
            reverse('blog:dashboard'),
            fetch_redirect_response=False,
        )
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.successful_login_count, 1)
        old_record = UserLoginSession.objects.get(
            user=self.user,
            is_active=True,
            tracking_id_digest__isnull=False,
        )

        response = self.login(replacement_browser)
        self.assertRedirects(
            response,
            reverse('blog:manage_active_sessions'),
            fetch_redirect_response=False,
        )
        self.assertNotIn('_auth_user_id', replacement_browser.session)
        self.assertEqual(
            self.user.pending_login_selections.count(),
            1,
        )
        response = replacement_browser.get(reverse('blog:manage_active_sessions'))
        self.assertContains(
            response,
            'Your active login limit has been reached. Log out an existing session to continue in this window.',
        )
        self.assertContains(response, old_record.device_description)
        self.assertContains(response, 'Login time:')
        self.assertContains(response, 'Last activity:')
        self.assertNotContains(response, old_record.tracking_id_digest)

        response = replacement_browser.post(
            reverse('blog:replace_active_session'),
            {'active_session_id': old_record.pk},
        )
        self.assertRedirects(
            response,
            reverse('blog:dashboard'),
            fetch_redirect_response=False,
        )
        old_record.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertFalse(old_record.is_active)
        self.assertEqual(self.profile.successful_login_count, 2)
        self.assertEqual(
            UserLoginSession.objects.filter(
                user=self.user,
                is_active=True,
                tracking_id_digest__isnull=False,
            ).count(),
            1,
        )

        revoked_response = original_browser.get(reverse('blog:dashboard'))
        self.assertRedirects(
            revoked_response,
            reverse('blog:login'),
            fetch_redirect_response=False,
        )
        self.assertNotIn('_auth_user_id', original_browser.session)

    def test_total_login_allowance_cannot_be_bypassed_by_replacement(self):
        self.profile.max_successful_logins = 1
        self.profile.save(update_fields=('max_successful_logins',))
        original_browser = Client()
        second_browser = Client()
        self.login(original_browser)
        old_record = UserLoginSession.objects.get(
            user=self.user,
            is_active=True,
            tracking_id_digest__isnull=False,
        )

        response = self.login(second_browser)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your total successful login allowance has been exhausted.')
        self.assertEqual(self.user.pending_login_selections.count(), 0)

        response = second_browser.post(
            reverse('blog:replace_active_session'),
            {'active_session_id': old_record.pk},
        )
        self.assertRedirects(response, reverse('blog:login'), fetch_redirect_response=False)
        old_record.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertTrue(old_record.is_active)
        self.assertEqual(self.profile.successful_login_count, 1)

    def test_expired_sessions_do_not_consume_concurrent_capacity(self):
        expired_at = timezone.now() - timedelta(minutes=1)
        UserLoginSession.objects.create(
            user=self.user,
            tracking_id_digest='a' * 64,
            device_description='Expired browser',
            login_at=expired_at - timedelta(hours=1),
            last_activity_at=expired_at - timedelta(minutes=1),
            expires_at=expired_at,
        )

        response = self.login(Client())
        self.assertRedirects(response, reverse('blog:dashboard'), fetch_redirect_response=False)
        self.assertEqual(
            UserLoginSession.objects.filter(user=self.user, is_active=True).count(),
            1,
        )

    @override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies')
    def test_signed_cookie_session_backend_tracks_and_revokes_sessions(self):
        self.profile.onboarding_completed = True
        self.profile.save(update_fields=('onboarding_completed',))
        browser = Client()

        response = self.login(browser)

        self.assertRedirects(
            response,
            reverse('blog:dashboard'),
            fetch_redirect_response=False,
        )
        self.assertEqual(browser.get(reverse('blog:dashboard')).status_code, 200)
        tracked_session = UserLoginSession.objects.get(
            user=self.user,
            is_active=True,
            tracking_id_digest__isnull=False,
        )

        browser.post(reverse('blog:logout'))

        tracked_session.refresh_from_db()
        self.assertFalse(tracked_session.is_active)

    def test_blank_concurrent_limit_allows_multiple_active_sessions(self):
        self.profile.max_active_sessions = None
        self.profile.save(update_fields=('max_active_sessions',))

        response_one = self.login(Client())
        response_two = self.login(Client())

        self.assertRedirects(
            response_one,
            reverse('blog:dashboard'),
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            response_two,
            reverse('blog:dashboard'),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            UserLoginSession.objects.filter(
                user=self.user,
                is_active=True,
                tracking_id_digest__isnull=False,
            ).count(),
            2,
        )

    def test_expired_pending_login_cannot_replace_a_session(self):
        original_browser = Client()
        pending_browser = Client()
        self.login(original_browser)
        self.login(pending_browser)
        pending = PendingUserLogin.objects.get(user=self.user)
        PendingUserLogin.objects.filter(pk=pending.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        response = pending_browser.get(reverse('blog:manage_active_sessions'))
        self.assertRedirects(response, reverse('blog:login'), fetch_redirect_response=False)
        self.assertEqual(self.user.tracked_login_sessions.filter(
            is_active=True,
            tracking_id_digest__isnull=False,
        ).count(), 1)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.successful_login_count, 1)

    def test_cancel_removes_pending_login_without_counting_it(self):
        active_browser = Client()
        pending_browser = Client()
        self.login(active_browser)
        self.login(pending_browser)
        self.assertEqual(self.user.pending_login_selections.count(), 1)

        response = pending_browser.post(reverse('blog:cancel_pending_login'))
        self.assertRedirects(response, reverse('blog:login'), fetch_redirect_response=False)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.successful_login_count, 1)
        self.assertEqual(self.user.pending_login_selections.count(), 0)
        self.assertNotIn('_auth_user_id', pending_browser.session)

    def test_normal_logout_removes_tracked_session(self):
        browser = Client()
        self.login(browser)
        tracked_session = UserLoginSession.objects.get(
            user=self.user,
            is_active=True,
            tracking_id_digest__isnull=False,
        )

        response = browser.post(reverse('blog:logout'))

        self.assertRedirects(response, reverse('blog:home'), fetch_redirect_response=False)
        tracked_session.refresh_from_db()
        self.assertFalse(tracked_session.is_active)
        self.assertIsNotNone(tracked_session.revoked_at)

    def test_admin_can_revoke_an_individual_session(self):
        browser = Client()
        self.login(browser)
        tracked_session = UserLoginSession.objects.get(
            user=self.user,
            is_active=True,
            tracking_id_digest__isnull=False,
        )
        admin_request = RequestFactory().post('/admin/blog/userloginsession/')
        admin_request.user = User.objects.create_superuser(
            'session-admin',
            email='session-admin@example.test',
            password='AdminPassword!123',
        )
        model_admin = UserLoginSessionAdmin(UserLoginSession, AdminSite())

        with patch.object(model_admin, 'message_user'):
            model_admin.revoke_selected_sessions(
                admin_request,
                UserLoginSession.objects.filter(pk=tracked_session.pk),
            )

        tracked_session.refresh_from_db()
        self.assertFalse(tracked_session.is_active)
        self.assertIsNotNone(tracked_session.revoked_at)
        response = browser.get(reverse('blog:dashboard'))
        self.assertRedirects(response, reverse('blog:login'), fetch_redirect_response=False)

    def test_replacement_post_requires_csrf_validation(self):
        original_browser = Client()
        self.login(original_browser)

        pending_browser = Client(enforce_csrf_checks=True)
        response = pending_browser.get(reverse('blog:login'))
        self.assertEqual(response.status_code, 200)
        csrf_token = pending_browser.cookies['csrftoken'].value
        response = pending_browser.post(
            reverse('blog:login'),
            {'username': self.user.username, 'password': 'StrongPassword!123'},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertRedirects(
            response,
            reverse('blog:manage_active_sessions'),
            fetch_redirect_response=False,
        )
        pending_browser.get(reverse('blog:manage_active_sessions'))
        response = pending_browser.post(
            reverse('blog:replace_active_session'),
            {'active_session_id': 1},
        )
        self.assertEqual(response.status_code, 403)

    def _google_request(self):
        request = RequestFactory().get('/accounts/google/login/callback/')
        session_store = importlib.import_module(settings.SESSION_ENGINE).SessionStore
        request.session = session_store()
        request.session.create()
        request.user = AnonymousUser()
        request.META['HTTP_USER_AGENT'] = 'Mozilla/5.0 Chrome/123.0 Windows'
        return request

    def test_google_login_adapter_uses_same_concurrent_limit(self):
        request = self._google_request()
        social_adapter = BlogSocialAccountAdapter()
        account_adapter = BlogAccountAdapter()
        social_adapter.pre_social_login(request, SimpleNamespace())

        account_adapter.login(request, self.user)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.successful_login_count, 1)
        self.assertEqual(
            UserLoginSession.objects.filter(
                user=self.user,
                is_active=True,
                tracking_id_digest=session_tracking_digest(request.session),
            ).count(),
            1,
        )

    def test_google_login_at_limit_shows_session_selection_without_authenticating(self):
        original_browser = Client()
        self.login(original_browser)
        old_record = UserLoginSession.objects.get(
            user=self.user,
            is_active=True,
            tracking_id_digest__isnull=False,
        )
        request = self._google_request()
        BlogSocialAccountAdapter().pre_social_login(request, SimpleNamespace())

        with self.assertRaises(ImmediateHttpResponse) as raised:
            BlogAccountAdapter().login(request, self.user)

        self.assertEqual(
            raised.exception.response['Location'],
            reverse('blog:manage_active_sessions'),
        )
        self.assertNotIn('_auth_user_id', request.session)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.successful_login_count, 1)
        self.assertEqual(self.user.pending_login_selections.count(), 1)

        request.session.save()
        replacement_browser = Client()
        replacement_browser.cookies[settings.SESSION_COOKIE_NAME] = (
            request.session.session_key
        )
        response = replacement_browser.get(reverse('blog:manage_active_sessions'))
        self.assertEqual(response.status_code, 200)
        response = replacement_browser.post(
            reverse('blog:replace_active_session'),
            {'active_session_id': old_record.pk},
        )
        self.assertRedirects(
            response,
            reverse('blog:dashboard'),
            fetch_redirect_response=False,
        )
        old_record.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertFalse(old_record.is_active)
        self.assertEqual(self.profile.successful_login_count, 2)
