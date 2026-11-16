from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.core.cache import cache
from unittest.mock import patch

from ai.services import validate_feature_json
from blog.models import CommunityFollow, CommunityPost, CommunityReply, CommunityReport, Project, SiteSettings, XPEvent


class CommunityAndAIFeatureTests(TestCase):
    def setUp(self):
        cache.clear()
        user_model = get_user_model()
        self.author = user_model.objects.create_user('question-author', password='test-pass-123')
        self.answerer = user_model.objects.create_user('answer-author', password='test-pass-123')
        self.staff = user_model.objects.create_user('moderator', password='test-pass-123', is_staff=True)
        self.post = CommunityPost.objects.create(
            author=self.author,
            title='How do I test this?',
            content='I need help with a test.',
        )
        self.reply = CommunityReply.objects.create(
            post=self.post,
            author=self.answerer,
            content='Use the Django test client.',
        )
        self.project = Project.objects.create(
            owner=self.author,
            title='Smoke project',
            short_description='A project test.',
            description='A project description.',
            category='Web',
        )

    def test_only_question_author_can_accept_an_answer_and_xp_is_awarded_once(self):
        self.client.force_login(self.answerer)
        response = self.client.post(reverse('blog:community_accept_answer', args=(self.post.pk, self.reply.pk)))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.author)
        accepted = self.client.post(reverse('blog:community_accept_answer', args=(self.post.pk, self.reply.pk)))
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(self.post.__class__.objects.get(pk=self.post.pk).accepted_reply_id, self.reply.pk)
        self.assertEqual(XPEvent.objects.filter(user=self.answerer, source_type='accepted_community_answer').count(), 1)
        self.client.post(reverse('blog:community_accept_answer', args=(self.post.pk, self.reply.pk)))
        self.assertEqual(XPEvent.objects.filter(user=self.answerer, source_type='accepted_community_answer').count(), 1)

    def test_community_follow_and_report_are_idempotent(self):
        self.client.force_login(self.answerer)
        follow_url = reverse('blog:community_follow', args=(self.post.pk,))
        self.client.post(follow_url)
        self.client.post(follow_url)
        self.assertEqual(CommunityFollow.objects.filter(post=self.post, user=self.answerer).count(), 1)

        report_url = reverse('blog:community_report')
        self.client.post(report_url, {'post_id': self.post.pk, 'reason': 'Spam'})
        self.client.post(report_url, {'post_id': self.post.pk, 'reason': 'Spam'})
        self.assertEqual(CommunityReport.objects.filter(post=self.post, reporter=self.answerer).count(), 1)

    def test_moderation_is_staff_only(self):
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(reverse('blog:community_moderation')).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('blog:community_moderation')).status_code, 200)

    def test_disabled_ai_feature_returns_forbidden(self):
        settings = SiteSettings.get_cached()
        settings.ai_enabled = False
        settings.save()
        self.client.force_login(self.author)
        response = self.client.post(reverse('blog:ai_feature', args=('assistant',)), {'prompt': 'Help me.'})
        self.assertEqual(response.status_code, 403)

    def test_username_check_and_export_are_scoped(self):
        response = self.client.get(reverse('blog:username_available'), {'username': self.answerer.username})
        self.assertFalse(response.json()['available'])
        self.client.force_login(self.author)
        exported = self.client.get(reverse('blog:export_user_data')).json()
        self.assertEqual(exported['account']['username'], self.author.username)
        self.assertNotIn(self.answerer.username, str(exported))

    def test_profile_details_and_notification_preferences_are_saved(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse('blog:profile'), {
            'profile_details': '1',
            'display_name': 'Learning Author',
            'headline': 'Python learner',
            'location': 'Remote',
            'bio': 'Learning every day.',
            'skills': 'Python, Django',
            'github_url': '',
            'linkedin_url': '',
            'portfolio_url': '',
        })
        self.assertEqual(response.status_code, 302)
        self.author.profile_data.refresh_from_db()
        self.assertEqual(self.author.profile_data.skills, ['Python', 'Django'])

        self.client.post(reverse('blog:settings'), {
            'notification_preferences': '1',
            'notify_community': 'on',
            'notify_follows': 'on',
        })
        self.author.profile_data.refresh_from_db()
        self.assertTrue(self.author.profile_data.notify_community)
        self.assertFalse(self.author.profile_data.notify_messages)

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'configured-test-key', 'AI_MODEL_BALANCED': 'test-model'})
    @patch('blog.views.complete_feature', return_value={'answer': 'A useful explanation.'})
    def test_ai_feature_cache_avoids_a_second_provider_call(self, provider):
        self.client.force_login(self.author)
        url = reverse('blog:ai_feature', args=('assistant',))
        payload = {'prompt': 'Explain a list.'}
        self.assertEqual(self.client.post(url, payload).status_code, 200)
        cached_response = self.client.post(url, payload)
        self.assertTrue(cached_response.json()['cached'])
        self.assertEqual(provider.call_count, 1)

    def test_ai_context_cannot_read_another_users_private_project(self):
        self.project.is_public = False
        self.project.save(update_fields=('is_public',))
        self.client.force_login(self.answerer)
        response = self.client.post(reverse('blog:ai_feature', args=('assistant',)), {
            'prompt': 'Explain this project.',
            'object_type': 'project',
            'object_id': self.project.pk,
        })
        self.assertEqual(response.status_code, 404)

    def test_ai_schema_rejects_malformed_responses(self):
        with self.assertRaises(ValueError):
            validate_feature_json('assistant', {'answer': ['not text']})

    def test_project_community_and_public_profile_pages_render_cleanly(self):
        self.client.force_login(self.author)
        urls = (
            reverse('blog:project_detail', args=(self.project.pk,)),
            reverse('blog:community_post_detail', args=(self.post.pk,)),
            reverse('blog:public_user_profile', args=(self.author.username,)),
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assertNotIn('{{', html)
                self.assertNotIn('{%', html)

        profile_response = self.client.get(
            reverse('blog:public_user_profile', args=(self.author.username,))
        )
        self.assertEqual(profile_response.context['post_count'], 1)
        self.assertContains(profile_response, self.post.title)

    def test_profile_projects_tab_renders_the_selected_projects(self):
        self.client.force_login(self.author)

        response = self.client.get(reverse('blog:profile'), {'tab': 'projects'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_tab'], 'projects')
        self.assertContains(response, self.project.title)
