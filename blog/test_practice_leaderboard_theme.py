from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class PracticeLeaderboardThemeTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            username='leaderboard-user',
            password='StrongPassword!123',
        )
        self.client.force_login(user)

    def test_leaderboard_loads_light_theme_styles_and_clear_empty_state(self):
        response = self.client.get(reverse('blog:practice_leaderboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '/static/css/practice_leaderboard.css?v=20261009-1',
        )
        self.assertContains(response, 'Leaderboard period')
        self.assertContains(response, 'No ranking data is available yet.')

    def test_period_filter_marks_the_selected_period(self):
        response = self.client.get(
            reverse('blog:practice_leaderboard'),
            {'period': 'week'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Weekly')
        self.assertContains(response, 'aria-current="page"')
