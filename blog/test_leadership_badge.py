from datetime import date

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .admin import UserProfileAdmin
from .models import UserProfile


class LeadershipBadgeDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='badge-user',
            password='StrongPassword!123',
        )
        self.profile = self.user.profile_data
        self.profile.display_name = 'Taylor Learner'
        self.profile.onboarding_completed = True
        self.profile.save(update_fields=('display_name', 'onboarding_completed'))
        self.client.force_login(self.user)

    def test_dashboard_shows_compact_unawarded_state(self):
        response = self.client.get(reverse('blog:dashboard'))

        self.assertContains(response, 'No leadership badge awarded yet')
        self.assertNotContains(response, 'leadership-badge-card')

    def test_dashboard_shows_only_current_users_database_award_details(self):
        self.profile.leadership_badge_awarded = True
        self.profile.leadership_badge_title = 'Community Leader'
        self.profile.leadership_badge_description = (
            'Recognized for helping others learn and grow.'
        )
        self.profile.leadership_badge_awarded_at = date(2026, 10, 8)
        self.profile.save()
        other_user = User.objects.create_user(
            username='another-user',
            password='StrongPassword!123',
        )
        other_user.profile_data.onboarding_completed = True
        other_user.profile_data.save(update_fields=('onboarding_completed',))

        response = self.client.get(reverse('blog:dashboard'))

        self.assertContains(response, 'Community Leader')
        self.assertContains(response, 'Taylor Learner')
        self.assertContains(
            response,
            'Recognized for helping others learn and grow.',
        )
        self.assertContains(response, 'October 8, 2026')
        self.assertNotContains(response, other_user.username)

        other_client = self.client_class()
        other_client.force_login(other_user)
        other_response = other_client.get(reverse('blog:dashboard'))
        self.assertContains(
            other_response,
            'No leadership badge awarded yet',
        )
        self.assertNotContains(other_response, 'Community Leader')

    def test_admin_can_manage_badge_but_awarded_badge_requires_complete_details(self):
        profile_admin = admin.site._registry[UserProfile]
        admin_user = User.objects.create_superuser(
            username='badge-admin',
            email='badge-admin@example.test',
            password='StrongPassword!123',
        )
        request = type('AdminRequest', (), {'user': admin_user})()
        form = profile_admin.get_form(request)

        self.assertIn('leadership_badge_awarded', form.base_fields)
        self.assertIn('leadership_badge_title', form.base_fields)
        self.assertIn('leadership_badge_description', form.base_fields)
        self.assertIn('leadership_badge_awarded_at', form.base_fields)
        self.assertIsInstance(profile_admin, UserProfileAdmin)

        self.profile.leadership_badge_awarded = True
        with self.assertRaises(ValidationError):
            self.profile.full_clean()

    def test_regular_user_cannot_award_or_edit_badge_through_settings(self):
        response = self.client.post(
            reverse('blog:settings'),
            {
                'is_private': 'on',
                'leadership_badge_awarded': 'on',
                'leadership_badge_title': 'Self-awarded',
                'leadership_badge_description': 'Not an admin award.',
                'leadership_badge_awarded_at': '2026-10-09',
            },
        )

        self.assertRedirects(response, reverse('blog:settings'))
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.leadership_badge_awarded)
        self.assertEqual(self.profile.leadership_badge_title, '')
