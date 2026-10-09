from django.conf import settings
from django.contrib import admin
from django.contrib.auth.signals import user_logged_in
from django.core.management import call_command
from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from unittest.mock import patch
from io import BytesIO
from tempfile import TemporaryDirectory
from datetime import timedelta
import hashlib

from PIL import Image

from .forms import EmailSignupForm
from .gmail_service import send_gmail
from .models import (
	Assignment,
	AssignmentAudience,
	AssignmentAttempt,
	AssignmentOption,
	AssignmentQuestion,
	AssignmentSubmission,
	FollowRequest,
	Notification,
	UserBlock,
	AITutorConversation,
	AITutorMessage,
	Enrollment,
	Conversation,
	Comment,
	CommunityPost,
	CommunityReply,
	Lesson,
	Post,
	PracticeProgress,
	PracticeSubmission,
	UserProfile,
	UserLoginSession,
)
from .admin import AssignmentSubmissionAdmin
from .consumers import ConversationConsumer


class HomeRedirectTests(TestCase):
	def test_anonymous_user_is_sent_to_existing_login_page(self):
		response = self.client.get(reverse('blog:home'))
		self.assertRedirects(response, reverse('blog:login'))

	def test_authenticated_user_reaches_dashboard_from_root(self):
		user = User.objects.create_user('home-user', password='pass')
		user.profile_data.onboarding_completed = True
		user.profile_data.save(update_fields=['onboarding_completed'])
		self.client.force_login(user)
		response = self.client.get(reverse('blog:home'), follow=True)

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'blog/dashboard.html')
		self.assertEqual(
			response.redirect_chain,
			[
				(reverse('blog:login'), 302),
				(reverse('blog:dashboard'), 302),
			],
		)

	def test_login_page_remains_available(self):
		response = self.client.get(reverse('blog:login'))
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'blog/login.html')

	def test_new_user_completes_goal_setup_once_and_can_change_goal(self):
		user = User.objects.create_user('goal-user', password='pass')
		self.client.force_login(user)

		response = self.client.get(reverse('blog:dashboard'))
		self.assertRedirects(response, reverse('blog:choose_goal'))

		goal_page = self.client.get(reverse('blog:choose_goal'))
		self.assertEqual(goal_page.status_code, 200)
		self.assertContains(goal_page, 'Learn Python')
		self.assertContains(goal_page, 'Become a Full Stack Developer')
		self.assertContains(goal_page, 'Other')

		response = self.client.post(
			reverse('blog:choose_goal'),
			{'goal': 'python'},
		)
		self.assertRedirects(response, reverse('blog:dashboard'))
		user.profile_data.refresh_from_db()
		self.assertEqual(user.profile_data.goal, 'python')
		self.assertTrue(user.profile_data.onboarding_completed)
		self.assertTemplateUsed(
			self.client.get(reverse('blog:dashboard')),
			'blog/dashboard.html',
		)

		self.client.post(reverse('blog:choose_goal'), {'goal': 'projects'})
		user.profile_data.refresh_from_db()
		self.assertEqual(user.profile_data.goal, 'projects')

	@patch('blog.signals.send_gmail')
	def test_email_login_still_redirects_to_dashboard(self, send_gmail):
		user = User.objects.create_user(
			'login-user',
			email='login@example.com',
			password='pass',
		)

		response = self.client.post(
			reverse('blog:login'),
			{'username': user.email, 'password': 'pass'},
		)

		self.assertRedirects(response, reverse('blog:dashboard'), fetch_redirect_response=False)
		send_gmail.assert_called_once()
		email_args = send_gmail.call_args.args
		self.assertEqual(email_args[1], 'New login to your vGrowHub account')
		self.assertIn('@login-user', email_args[2])
		self.assertIn('Login method: Password', email_args[2])
		self.assertIn('Login time:', email_args[2])

	@patch('blog.signals.send_gmail', side_effect=RuntimeError('mail unavailable'))
	def test_email_failure_does_not_block_password_login(self, send_gmail):
		user = User.objects.create_user(
			'resilient-login',
			email='resilient@example.com',
			password='pass',
		)

		with self.assertLogs('blog.signals', level='ERROR') as logs:
			response = self.client.post(
				reverse('blog:login'),
				{'username': user.username, 'password': 'pass'},
			)

		self.assertRedirects(response, reverse('blog:dashboard'), fetch_redirect_response=False)
		send_gmail.assert_called_once()
		self.assertIn('mail unavailable', '\n'.join(logs.output))

	@patch('blog.signals.send_gmail')
	def test_google_login_signal_sends_one_security_email(self, send_gmail):
		user = User.objects.create_user(
			'google-login-user',
			email='google@example.com',
			password='pass',
		)
		request = RequestFactory().get('/accounts/google/login/callback/')
		request.session = {}

		user_logged_in.send(sender=User, request=request, user=user)
		user_logged_in.send(sender=User, request=request, user=user)

		send_gmail.assert_called_once()
		self.assertEqual(
			send_gmail.call_args.args[1],
			'New login to your vGrowHub account',
		)
		self.assertIn('Login method: Google', send_gmail.call_args.args[2])


class EmailServiceTests(TestCase):
	@override_settings(
		EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
		DEFAULT_FROM_EMAIL='noreply@vgrowhub.example',
	)
	def test_existing_email_helper_uses_configured_django_backend(self):
		mail.outbox = []
		result = send_gmail(
			'learner@example.test',
			'Welcome',
			'Your account was created.',
		)

		self.assertEqual(result, 1)
		self.assertEqual(len(mail.outbox), 1)
		self.assertEqual(mail.outbox[0].from_email, 'noreply@vgrowhub.example')
		self.assertEqual(mail.outbox[0].to, ['learner@example.test'])
		self.assertNotIn('password', mail.outbox[0].body.lower())

	@patch('blog.views.send_gmail')
	def test_signup_success_message_uses_production_login_url(self, send_gmail):
		response = self.client.post(
			reverse('blog:signup'),
			{
				'username': 'newuser',
				'email': 'newuser@example.com',
				'password1': 'VeryStrongPass!123',
				'password2': 'VeryStrongPass!123',
			},
			follow=True,
		)

		self.assertContains(response, 'Account created successfully! 🎉')
		self.assertContains(response, 'We’ve sent your welcome email')
		send_gmail.assert_called_once()
		self.assertIn(settings.SITE_BASE_URL + '/login/', send_gmail.call_args.args[2])
		self.assertNotIn('127.0.0.1', send_gmail.call_args.args[2])

	@patch('blog.views.send_gmail')
	def test_forgot_password_success_shows_professional_reset_message(self, send_gmail):
		user = User.objects.create_user(
			'otpuser',
			email='otpuser@example.com',
			password='StrongPassword!123',
		)

		response = self.client.post(
			reverse('blog:forgot_password'),
			{'email': user.email},
			follow=True,
		)

		self.assertContains(response, 'Check your email 📩')
		self.assertContains(response, 'Enter the OTP here to continue resetting your password.')
		send_gmail.assert_called_once()
		self.assertEqual(send_gmail.call_args.args[1], 'vGrowHub Password Reset OTP')
		self.assertNotIn('127.0.0.1', send_gmail.call_args.args[2])


class PasswordChangeTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			'password-change-user',
			password='OldPassword73!Secure',
		)
		self.user.profile_data.onboarding_completed = True
		self.user.profile_data.save(update_fields=['onboarding_completed'])
		self.client.force_login(self.user)

	def test_password_change_validates_current_password_and_keeps_session(self):
		response = self.client.post(
			reverse('blog:change_password'),
			{
				'old_password': 'OldPassword73!Secure',
				'new_password1': 'CobaltMaple!4821River',
				'new_password2': 'CobaltMaple!4821River',
			},
		)

		self.assertRedirects(response, reverse('blog:settings'))
		self.user.refresh_from_db()
		self.assertTrue(self.user.check_password('CobaltMaple!4821River'))
		self.assertEqual(self.client.get(reverse('blog:settings')).status_code, 200)

	def test_password_change_rejects_wrong_current_password(self):
		response = self.client.post(
			reverse('blog:change_password'),
			{
				'old_password': 'incorrect',
				'new_password1': 'CobaltMaple!4821River',
				'new_password2': 'CobaltMaple!4821River',
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context['form'].has_error('old_password'))

	def test_google_only_user_gets_password_unavailable_message(self):
		user = User.objects.create_user('google-only-user')
		user.set_unusable_password()
		user.save(update_fields=['password'])
		self.client.force_login(user)

		response = self.client.get(reverse('blog:change_password'))

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context['password_unavailable'])


class AccountLifecycleTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			'lifecycle-user',
			email='lifecycle@example.com',
			password='LifecyclePassword82!Safe',
		)
		self.user.profile_data.onboarding_completed = True
		self.user.profile_data.save(update_fields=['onboarding_completed'])

	@patch('blog.signals.send_gmail')
	def test_temporary_deactivation_blocks_features_and_can_be_reversed(self, send_gmail):
		self.client.force_login(self.user)
		response = self.client.post(
			reverse('blog:deactivate_account'),
			{
				'confirmation': 'DEACTIVATE',
				'password': 'LifecyclePassword82!Safe',
			},
		)
		self.assertRedirects(response, reverse('blog:account_recovery'))

		self.user.profile_data.refresh_from_db()
		self.assertTrue(self.user.profile_data.is_deactivated)
		self.assertEqual(
			self.client.get(
				reverse('blog:user_profile', args=[self.user.username])
			).status_code,
			404,
		)
		viewer = User.objects.create_user('lifecycle-viewer', password='pass')
		self.client.force_login(viewer)
		follow_response = self.client.post(
			reverse('blog:send_follow_request', args=[self.user.username]),
		)
		self.assertEqual(follow_response.status_code, 404)
		self.client.logout()
		self.client.post(
			reverse('blog:login'),
			{
				'username': self.user.username,
				'password': 'LifecyclePassword82!Safe',
			},
		)
		self.assertRedirects(
			self.client.get(reverse('blog:dashboard')),
			reverse('blog:account_recovery'),
		)

		response = self.client.post(
			reverse('blog:account_recovery'),
			{
				'action': 'reactivate',
				'password': 'LifecyclePassword82!Safe',
			},
		)
		self.assertRedirects(response, reverse('blog:settings'))
		self.user.profile_data.refresh_from_db()
		self.assertFalse(self.user.profile_data.is_deactivated)
		self.assertIsNone(self.user.profile_data.deactivated_at)
		self.assertEqual(send_gmail.call_count, 2)

	@patch('blog.signals.send_gmail')
	def test_deletion_is_scheduled_and_can_be_cancelled(self, send_gmail):
		self.client.force_login(self.user)
		response = self.client.post(
			reverse('blog:request_account_deletion'),
			{
				'confirmation': 'DELETE',
				'password': 'LifecyclePassword82!Safe',
			},
		)
		self.assertRedirects(response, reverse('blog:account_recovery'))

		self.user.profile_data.refresh_from_db()
		self.assertTrue(self.user.profile_data.is_deactivated)
		self.assertIsNotNone(self.user.profile_data.deletion_requested_at)
		self.assertGreaterEqual(
			self.user.profile_data.scheduled_deletion_at,
			timezone.now() + timedelta(days=29),
		)

		self.client.post(
			reverse('blog:login'),
			{
				'username': self.user.username,
				'password': 'LifecyclePassword82!Safe',
			},
		)
		response = self.client.post(
			reverse('blog:account_recovery'),
			{
				'action': 'cancel_deletion',
				'password': 'LifecyclePassword82!Safe',
			},
		)
		self.assertRedirects(response, reverse('blog:settings'))
		self.user.profile_data.refresh_from_db()
		self.assertFalse(self.user.profile_data.is_deactivated)
		self.assertIsNone(self.user.profile_data.scheduled_deletion_at)
		self.assertEqual(send_gmail.call_count, 2)

	def test_cleanup_command_only_deletes_due_accounts(self):
		profile = self.user.profile_data
		profile.is_deactivated = True
		profile.deletion_requested_at = timezone.now() - timedelta(days=31)
		profile.scheduled_deletion_at = timezone.now() - timedelta(days=1)
		profile.save(update_fields=[
			'is_deactivated',
			'deletion_requested_at',
			'scheduled_deletion_at',
		])

		call_command('purge_scheduled_accounts', dry_run=True)
		self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

		call_command('purge_scheduled_accounts')
		self.assertFalse(User.objects.filter(pk=self.user.pk).exists())


class PeopleDiscoveryTests(TestCase):
	def setUp(self):
		self.viewer = User.objects.create_user('search-viewer', password='pass')
		self.person = User.objects.create_user('victorpaul', password='pass')
		UserProfile.objects.update_or_create(
			user=self.person,
			defaults={'display_name': 'Victor Paul'},
		)
		self.client.force_login(self.viewer)

	def test_people_page_waits_for_search_query(self):
		response = self.client.get(reverse('blog:discover_users'))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['users'], [])
		self.assertContains(response, 'Enter a name or username to discover people.')

	def test_people_search_matches_display_name_and_at_username(self):
		for query in ('victor', '@VICTORPAUL'):
			with self.subTest(query=query):
				response = self.client.get(
					reverse('blog:discover_users'),
					{'q': query},
				)
				self.assertEqual(
					[person.id for person in response.context['users']],
					[self.person.id],
				)
				self.assertContains(response, 'Victor Paul')
				self.assertContains(response, '@victorpaul')


class UsernameIdentityTests(TestCase):
	def test_signup_form_uses_username_identity_and_photo_crop_ui(self):
		response = self.client.get(reverse('blog:signup'))

		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, 'Display Name')
		self.assertContains(response, 'Username')
		self.assertContains(response, 'Crop &amp; Use Photo')
		self.assertContains(response, 'photo_cropper.js')

	def test_signup_uses_normalized_username_as_display_identity(self):
		form = EmailSignupForm(data={
			'email': 'victor@example.com',
			'username': '@Victor_Paul',
			'password1': 'IndigoRiver74!Secure',
			'password2': 'IndigoRiver74!Secure',
		})

		self.assertNotIn('display_name', form.fields)
		self.assertTrue(form.is_valid(), form.errors)
		user = form.save()
		user.profile_data.refresh_from_db()

		self.assertEqual(user.username, 'victor_paul')
		self.assertEqual(user.profile_data.display_name, 'victor_paul')

	@patch('blog.signals.send_gmail')
	@patch('blog.views.send_gmail')
	def test_signup_uploads_optional_profile_picture(self, send_welcome_email, send_login_email):
		image_data = BytesIO()
		Image.new('RGB', (2, 2), color='purple').save(image_data, format='PNG')
		image = SimpleUploadedFile(
			'profile.png',
			image_data.getvalue(),
			content_type='image/png',
		)

		with TemporaryDirectory() as media_root:
			with override_settings(MEDIA_ROOT=media_root):
				response = self.client.post(
					reverse('blog:signup'),
					{
						'email': 'picture@example.com',
						'username': 'picture_user',
						'password1': 'IndigoRiver74!Secure',
						'password2': 'IndigoRiver74!Secure',
						'profile_picture': image,
					},
				)

				self.assertRedirects(
					response,
					reverse('blog:login'),
					fetch_redirect_response=False,
				)
				user = User.objects.get(username='picture_user')
				user.profile_data.refresh_from_db()
				self.assertTrue(user.profile_data.profile_picture)
				self.assertTrue(user.profile_data.profile_picture.storage.exists(
					user.profile_data.profile_picture.name
				))
				self.client.force_login(user)
				profile_response = self.client.get(reverse('blog:profile'))
				self.assertContains(profile_response, 'Change Profile Picture')
				self.assertContains(
					profile_response,
					user.profile_data.profile_picture.url,
				)

		send_welcome_email.assert_called_once()
		email_args = send_welcome_email.call_args.args
		self.assertEqual(email_args[1], 'Welcome to vGrowHub 🎉')
		self.assertIn('@picture_user', email_args[2])
		send_login_email.assert_called_once()
		self.assertEqual(
			send_login_email.call_args.args[1],
			'New login to your vGrowHub account',
		)

	def test_signup_rejects_non_image_profile_picture(self):
		response = self.client.post(
			reverse('blog:signup'),
			{
				'email': 'invalid-picture@example.com',
				'username': 'invalid_picture',
				'password1': 'IndigoRiver74!Secure',
				'password2': 'IndigoRiver74!Secure',
				'profile_picture': SimpleUploadedFile(
					'profile.txt',
					b'not an image',
					content_type='text/plain',
				),
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context['form'].has_error('profile_picture'))
		self.assertFalse(User.objects.filter(username='invalid_picture').exists())

	@patch('blog.views.send_gmail', side_effect=RuntimeError('mail unavailable'))
	def test_signup_email_failure_does_not_undo_account_creation(self, send_gmail):
		with self.assertLogs('blog.views', level='ERROR') as logs:
			response = self.client.post(
				reverse('blog:signup'),
				{
					'email': 'welcome@example.com',
					'username': 'welcome_user',
					'password1': 'IndigoRiver74!Secure',
					'password2': 'IndigoRiver74!Secure',
				},
			)

		self.assertRedirects(
			response,
			reverse('blog:login'),
			fetch_redirect_response=False,
		)
		self.assertTrue(User.objects.filter(username='welcome_user').exists())
		send_gmail.assert_called_once()
		self.assertIn('mail unavailable', '\n'.join(logs.output))

	def test_signup_rejects_disallowed_image_format(self):
		image_data = BytesIO()
		Image.new('RGB', (2, 2), color='purple').save(image_data, format='GIF')
		response = self.client.post(
			reverse('blog:signup'),
			{
				'email': 'gif@example.com',
				'username': 'gif_user',
				'password1': 'IndigoRiver74!Secure',
				'password2': 'IndigoRiver74!Secure',
				'profile_picture': SimpleUploadedFile(
					'profile.gif',
					image_data.getvalue(),
					content_type='image/gif',
				),
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context['form'].has_error('profile_picture'))
		self.assertFalse(User.objects.filter(username='gif_user').exists())

	def test_signup_rejects_uncropped_non_square_photo(self):
		image_data = BytesIO()
		Image.new('RGB', (4, 2), color='purple').save(image_data, format='PNG')
		response = self.client.post(
			reverse('blog:signup'),
			{
				'email': 'wide-photo@example.com',
				'username': 'wide_photo',
				'password1': 'IndigoRiver74!Secure',
				'password2': 'IndigoRiver74!Secure',
				'profile_picture': SimpleUploadedFile(
					'wide.png',
					image_data.getvalue(),
					content_type='image/png',
				),
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context['form'].has_error('profile_picture'))
		self.assertFalse(User.objects.filter(username='wide_photo').exists())

	def test_own_profile_picture_can_be_changed_and_removed(self):
		user = User.objects.create_user('picture-owner', password='pass')
		self.client.force_login(user)
		image_data = BytesIO()
		Image.new('RGB', (2, 2), color='purple').save(image_data, format='PNG')

		with TemporaryDirectory() as media_root:
			with override_settings(MEDIA_ROOT=media_root):
				response = self.client.post(
					reverse('blog:profile'),
					{
						'profile_picture': SimpleUploadedFile(
							'new-photo.png',
							image_data.getvalue(),
							content_type='image/png',
						),
						'remove_picture': '0',
					},
				)
				self.assertRedirects(
					response,
					reverse('blog:profile'),
					fetch_redirect_response=False,
				)
				user.profile_data.refresh_from_db()
				self.assertTrue(user.profile_data.profile_picture)
				self.assertTrue(user.profile_data.profile_picture.storage.exists(
					user.profile_data.profile_picture.name
				))

				response = self.client.post(
					reverse('blog:profile'),
					{'remove_picture': '1'},
				)
				self.assertRedirects(
					response,
					reverse('blog:profile'),
					fetch_redirect_response=False,
				)
				user.profile_data.refresh_from_db()
				self.assertFalse(user.profile_data.profile_picture)

	def test_profile_picture_post_to_another_users_profile_is_rejected(self):
		owner = User.objects.create_user('picture-other', password='pass')
		viewer = User.objects.create_user('picture-viewer', password='pass')
		self.client.force_login(viewer)
		response = self.client.post(
			reverse('blog:user_profile', args=[owner.username]),
			{'profile_picture': SimpleUploadedFile(
				'attack.png',
				b'not an image',
				content_type='image/png',
			)},
		)

		self.assertEqual(response.status_code, 405)
		profile = UserProfile.objects.filter(user=owner).first()
		self.assertFalse(profile and profile.profile_picture)

	def test_signup_rejects_unsafe_username_characters(self):
		form = EmailSignupForm(data={
			'email': 'victor@example.com',
			'username': 'victor paul',
			'password1': 'IndigoRiver74!Secure',
			'password2': 'IndigoRiver74!Secure',
		})

		self.assertFalse(form.is_valid())
		self.assertIn('username', form.errors)

	def test_profile_and_message_pages_show_display_name_and_handle(self):
		user = User.objects.create_user('profile-user', password='pass')
		other_user = User.objects.create_user('message-user', password='pass')
		user.profile_data.display_name = 'Profile User'
		user.profile_data.save(update_fields=['display_name'])
		other_user.profile_data.display_name = 'Message User'
		other_user.profile_data.save(update_fields=['display_name'])
		FollowRequest.objects.create(
			sender=user,
			receiver=other_user,
			status='ACCEPTED',
		)
		FollowRequest.objects.create(
			sender=other_user,
			receiver=user,
			status='ACCEPTED',
		)
		conversation = Conversation.objects.create(
			project_owner=user,
			participant=other_user,
		)

		self.client.force_login(user)
		profile_response = self.client.get(reverse('blog:profile'))
		self.assertContains(profile_response, 'Profile User')
		self.assertContains(profile_response, '@profile-user')

		messages_response = self.client.get(reverse('blog:messages'))
		self.assertContains(messages_response, 'Message User')
		self.assertContains(messages_response, '@message-user')

		chat_response = self.client.get(
			reverse('blog:conversation_detail', args=[conversation.pk])
		)
		self.assertContains(chat_response, 'Message User')
		self.assertContains(chat_response, '@message-user')
		self.assertContains(chat_response, 'id="typingIndicator"')
		self.assertContains(chat_response, 'aria-live="polite"')

	def test_database_rejects_case_insensitive_duplicate_usernames(self):
		User.objects.create_user('CaseSensitive', password='pass')
		with self.assertRaises(IntegrityError):
			with transaction.atomic():
				User.objects.create_user('casesensitive', password='pass')


class AccountPrivacyTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user('privacy-owner', password='pass')
		self.viewer = User.objects.create_user('privacy-viewer', password='pass')
		self.post = Post.objects.create(
			title='Private profile content',
			content='Visible to approved followers only.',
			author=self.owner,
		)

	def test_public_profile_is_visible_anonymously(self):
		response = self.client.get(
			reverse('blog:user_profile', args=[self.owner.username])
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Private profile content')

	def test_profile_routes_use_case_insensitive_username_and_redirect_legacy_ids(self):
		profile_url = reverse('blog:user_profile', args=[self.owner.username])
		self.assertEqual(profile_url, '/profile/privacy-owner/')
		self.assertEqual(
			self.client.get('/profile/PRIVACY-OWNER/').status_code,
			200,
		)
		legacy_response = self.client.get(f'/profile/{self.owner.pk}/')
		self.assertRedirects(
			legacy_response,
			profile_url,
			status_code=301,
			fetch_redirect_response=False,
		)

	def test_private_profile_hides_posts_from_unapproved_users(self):
		self.owner.profile_data.is_private = True
		self.owner.profile_data.save(update_fields=['is_private'])

		response = self.client.get(
			reverse('blog:user_profile', args=[self.owner.username])
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Private Account')
		self.assertNotContains(response, 'Private profile content')

	def test_private_profile_content_is_visible_to_accepted_followers(self):
		self.owner.profile_data.is_private = True
		self.owner.profile_data.save(update_fields=['is_private'])
		FollowRequest.objects.create(
			sender=self.viewer,
			receiver=self.owner,
			status='ACCEPTED',
		)
		self.client.force_login(self.viewer)

		response = self.client.get(
			reverse('blog:user_profile', args=[self.owner.username])
		)

		self.assertContains(response, 'Private profile content')

	def test_private_posts_are_hidden_in_lists_and_direct_views(self):
		self.owner.profile_data.is_private = True
		self.owner.profile_data.save(update_fields=['is_private'])
		self.client.force_login(self.viewer)

		list_response = self.client.get(reverse('blog:blogpage'))
		self.assertNotContains(list_response, 'Private profile content')

		detail_response = self.client.get(
			reverse('blog:post_detail', args=[self.post.slug])
		)
		self.assertEqual(detail_response.status_code, 403)

	def test_all_follow_requests_wait_for_receiver_approval(self):
		self.client.force_login(self.viewer)
		response = self.client.post(
			reverse('blog:send_follow_request', args=[self.owner.username])
		)

		self.assertEqual(response.json()['status'], 'PENDING')
		self.assertTrue(FollowRequest.objects.filter(
			sender=self.viewer,
			receiver=self.owner,
			status='PENDING',
		).exists())
		self.assertTrue(Notification.objects.filter(
			recipient=self.owner,
			notification_type='FOLLOW_REQUEST',
		).exists())
		self.assertFalse(FollowRequest.objects.filter(
			sender=self.viewer,
			receiver=self.owner,
			status='ACCEPTED',
		).exists())

	def test_cancel_after_accept_reports_stale_state_without_alert_response(self):
		request = FollowRequest.objects.create(
			sender=self.viewer,
			receiver=self.owner,
			status='ACCEPTED',
		)
		self.client.force_login(self.viewer)

		response = self.client.post(
			reverse('blog:cancel_follow_request', args=[self.owner.username]),
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)

		self.assertEqual(response.status_code, 409)
		self.assertEqual(
			response.json()['error'],
			'That follow request has already been processed.',
		)
		request.refresh_from_db()
		self.assertEqual(request.status, 'ACCEPTED')

	def test_notification_center_loads_requests_and_marks_items_read(self):
		follow_request = FollowRequest.objects.create(
			sender=self.viewer,
			receiver=self.owner,
			status='PENDING',
		)
		notification = Notification.objects.create(
			recipient=self.owner,
			sender=self.viewer,
			notification_type='FOLLOW_REQUEST',
			message='Follow request received.',
		)
		self.client.force_login(self.owner)

		response = self.client.get(reverse('blog:notifications'))

		self.assertContains(response, 'Accept')
		self.assertContains(response, 'Reject')
		self.assertContains(response, 'Follow Request')
		self.assertContains(
			response,
			reverse('blog:user_profile', args=[self.viewer.username]),
		)
		self.assertEqual(
			response.context['notifications'][0].pending_follow_request,
			follow_request,
		)

		response = self.client.post(
			reverse('blog:notifications'),
			{'notification_id': notification.id},
		)

		self.assertRedirects(response, reverse('blog:notifications'))
		notification.refresh_from_db()
		self.assertTrue(notification.is_read)

		other_notification = Notification.objects.create(
			recipient=self.owner,
			sender=self.viewer,
			notification_type='FOLLOW_REJECTED',
			message='Request declined.',
		)
		response = self.client.post(
			reverse('blog:notifications'),
			{'mark_all_read': '1'},
		)
		self.assertRedirects(response, reverse('blog:notifications'))
		other_notification.refresh_from_db()
		self.assertTrue(other_notification.is_read)

	def test_accepting_follow_request_from_notification_redirects_and_updates_state(self):
		follow_request = FollowRequest.objects.create(
			sender=self.viewer,
			receiver=self.owner,
			status='PENDING',
		)
		notification = Notification.objects.create(
			recipient=self.owner,
			sender=self.viewer,
			notification_type='FOLLOW_REQUEST',
			message='Follow request received.',
		)
		self.client.force_login(self.owner)

		response = self.client.post(
			reverse('blog:accept_follow_request', args=[follow_request.id])
		)

		self.assertRedirects(response, reverse('blog:notifications'))
		follow_request.refresh_from_db()
		notification.refresh_from_db()
		self.assertEqual(follow_request.status, 'ACCEPTED')
		self.assertTrue(notification.is_read)
		self.assertTrue(Notification.objects.filter(
			recipient=self.viewer,
			notification_type='FOLLOW_ACCEPTED',
		).exists())
		self.client.force_login(self.viewer)
		sender_profile = self.client.get(
			reverse('blog:user_profile', args=[self.owner.username]),
		)
		self.assertContains(sender_profile, 'Following')
		self.assertFalse(sender_profile.context['outgoing_pending'])
		self.client.force_login(self.owner)
		follow_back_profile = self.client.get(
			reverse('blog:user_profile', args=[self.viewer.username]),
		)
		self.assertContains(follow_back_profile, 'Follow Back')

	def test_blocking_hides_profile_and_prevents_follow_and_messaging(self):
		FollowRequest.objects.create(
			sender=self.viewer,
			receiver=self.owner,
			status='ACCEPTED',
		)
		self.client.force_login(self.viewer)

		response = self.client.post(
			reverse('blog:block_user', args=[self.owner.username])
		)

		self.assertRedirects(
			response,
			reverse('blog:user_profile', args=[self.owner.username]),
		)
		self.assertFalse(FollowRequest.objects.filter(
			sender=self.viewer,
			receiver=self.owner,
		).exists())
		self.assertTrue(UserBlock.objects.filter(
			blocker=self.viewer,
			blocked=self.owner,
		).exists())

		profile_response = self.client.get(
			reverse('blog:user_profile', args=[self.owner.username])
		)
		self.assertContains(profile_response, 'Unblock')
		self.assertNotContains(profile_response, 'Private profile content')
		self.assertEqual(
			self.client.post(
				reverse('blog:send_follow_request', args=[self.owner.username])
			).status_code,
			403,
		)
		self.assertEqual(
			self.client.post(
				reverse('blog:start_personal_chat', args=[self.owner.username])
			).status_code,
			403,
		)

		response = self.client.post(
			reverse('blog:unblock_user', args=[self.owner.username])
		)
		self.assertRedirects(
			response,
			reverse('blog:user_profile', args=[self.owner.username]),
		)
		self.assertFalse(UserBlock.objects.filter(
			blocker=self.viewer,
			blocked=self.owner,
		).exists())

	def test_blocked_user_cannot_open_blockers_profile(self):
		UserBlock.objects.create(blocker=self.owner, blocked=self.viewer)
		self.client.force_login(self.viewer)

		response = self.client.get(
			reverse('blog:user_profile', args=[self.owner.username])
		)

		self.assertEqual(response.status_code, 404)

	def test_personal_chat_and_new_message_require_mutual_follow(self):
		self.client.force_login(self.viewer)

		response = self.client.get(reverse('blog:messages'))
		self.assertNotContains(response, 'privacy-owner')
		self.assertEqual(
			self.client.post(
				reverse('blog:start_personal_chat', args=[self.owner.username])
			).status_code,
			403,
		)
		conversation = Conversation.objects.create(
			project_owner=self.viewer,
			participant=self.owner,
		)
		self.assertEqual(
			self.client.get(
				reverse('blog:conversation_detail', args=[conversation.pk])
			).status_code,
			403,
		)

		FollowRequest.objects.create(
			sender=self.viewer,
			receiver=self.owner,
			status='ACCEPTED',
		)
		FollowRequest.objects.create(
			sender=self.owner,
			receiver=self.viewer,
			status='ACCEPTED',
		)
		response = self.client.get(reverse('blog:messages'))
		self.assertContains(response, 'privacy-owner')
		self.assertEqual(
			self.client.post(
				reverse('blog:start_personal_chat', args=[self.owner.username])
			).status_code,
			200,
		)

	def test_people_search_links_to_profiles_and_excludes_blocked_users(self):
		self.owner.profile_data.display_name = 'Searchable Owner'
		self.owner.profile_data.save(update_fields=['display_name'])
		self.client.force_login(self.viewer)

		response = self.client.get(
			reverse('blog:discover_users'),
			{'q': 'Searchable'},
		)

		self.assertContains(response, 'Searchable Owner')
		self.assertContains(
			response,
			reverse('blog:user_profile', args=[self.owner.username]),
		)

		UserBlock.objects.create(blocker=self.viewer, blocked=self.owner)
		response = self.client.get(
			reverse('blog:discover_users'),
			{'q': 'Searchable'},
		)
		self.assertNotContains(response, 'Searchable Owner')

	def test_settings_can_toggle_private_account(self):
		self.client.force_login(self.owner)
		response = self.client.post(
			reverse('blog:settings'),
			{'is_private': 'on'},
		)

		self.assertRedirects(
			response,
			reverse('blog:settings'),
			fetch_redirect_response=False,
		)
		self.owner.profile_data.refresh_from_db()
		self.assertTrue(self.owner.profile_data.is_private)


class ConversationWebSocketTests(TransactionTestCase):
	def setUp(self):
		self.sender = User.objects.create_user('socket-sender', password='pass')
		self.receiver = User.objects.create_user('socket-receiver', password='pass')
		self.session_tokens = {}
		for user in (self.sender, self.receiver):
			tracking_id = f'test-session-{user.pk}'
			self.session_tokens[user.pk] = tracking_id
			UserLoginSession.objects.create(
				user=user,
				tracking_id_digest=hashlib.sha256(
					tracking_id.encode('utf-8'),
				).hexdigest(),
				expires_at=timezone.now() + timedelta(hours=1),
			)
		self.conversation = Conversation.objects.create(
			project_owner=self.sender,
			participant=self.receiver,
		)

	def _communicator(self, user):
		communicator = WebsocketCommunicator(
			ConversationConsumer.as_asgi(),
			f'/ws/messages/{self.conversation.id}/',
		)
		communicator.scope['user'] = user
		communicator.scope['session'] = {
			'_vgh_session_tracking_id': self.session_tokens[user.pk],
		}
		communicator.scope['url_route'] = {
			'kwargs': {'conversation_id': self.conversation.id},
		}
		return communicator

	def test_personal_websocket_rejects_non_mutual_followers(self):
		FollowRequest.objects.create(
			sender=self.sender,
			receiver=self.receiver,
			status='ACCEPTED',
		)
		communicator = self._communicator(self.sender)

		connected, close_code = async_to_sync(communicator.connect)()

		self.assertFalse(connected)
		self.assertEqual(close_code, 4403)

	def test_deactivated_account_cannot_subscribe_to_websocket(self):
		self.sender.profile_data.is_deactivated = True
		self.sender.profile_data.save(update_fields=['is_deactivated'])
		communicator = self._communicator(self.sender)

		connected, close_code = async_to_sync(communicator.connect)()

		self.assertFalse(connected)
		self.assertEqual(close_code, 4403)

	def test_mutual_followers_receive_websocket_message_events(self):
		FollowRequest.objects.create(
			sender=self.sender,
			receiver=self.receiver,
			status='ACCEPTED',
		)
		FollowRequest.objects.create(
			sender=self.receiver,
			receiver=self.sender,
			status='ACCEPTED',
		)
		communicator = self._communicator(self.sender)

		async def connect_and_receive():
			connected, _ = await communicator.connect()
			await get_channel_layer().group_send(
				f'conversation_{self.conversation.id}',
				{'type': 'chat.message', 'message_id': 47},
			)
			event = await communicator.receive_json_from()
			await communicator.disconnect()
			return connected, event

		connected, event = async_to_sync(connect_and_receive)()

		self.assertTrue(connected)
		self.assertEqual(event, {
			'type': 'message_created',
			'message_id': 47,
		})

	def test_chat_member_receives_typing_status_from_peer(self):
		FollowRequest.objects.create(
			sender=self.sender,
			receiver=self.receiver,
			status='ACCEPTED',
		)
		FollowRequest.objects.create(
			sender=self.receiver,
			receiver=self.sender,
			status='ACCEPTED',
		)
		sender_communicator = self._communicator(self.sender)
		receiver_communicator = self._communicator(self.receiver)

		async def connect_and_receive_typing():
			sender_connected, _ = await sender_communicator.connect()
			receiver_connected, _ = await receiver_communicator.connect()
			await sender_communicator.send_json_to({
				'type': 'typing',
				'is_typing': True,
				'user_id': self.receiver.pk,
			})
			start_event = await receiver_communicator.receive_json_from()
			await sender_communicator.send_json_to({
				'type': 'typing',
				'is_typing': False,
			})
			stop_event = await receiver_communicator.receive_json_from()
			await sender_communicator.disconnect()
			await receiver_communicator.disconnect()
			return sender_connected, receiver_connected, start_event, stop_event

		sender_connected, receiver_connected, start_event, stop_event = async_to_sync(
			connect_and_receive_typing,
		)()

		self.assertTrue(sender_connected)
		self.assertTrue(receiver_connected)
		self.assertEqual(start_event, {
			'type': 'typing_status',
			'user_id': self.sender.pk,
			'is_typing': True,
		})
		self.assertEqual(stop_event, {
			'type': 'typing_status',
			'user_id': self.sender.pk,
			'is_typing': False,
		})


class LogoutRedirectTests(TestCase):
	def test_post_logout_redirects_to_public_home(self):
		user = User.objects.create_user('logout-user', password='pass')
		self.client.force_login(user)

		response = self.client.post(reverse('blog:logout'))

		self.assertRedirects(response, reverse('blog:home'), fetch_redirect_response=False)
		self.assertNotIn('_auth_user_id', self.client.session)


class PasswordResetFlowTests(TestCase):
	@override_settings(
		EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
		EMAIL_HOST_USER='sender@example.com',
		EMAIL_HOST_PASSWORD='test-password',
		DEFAULT_FROM_EMAIL='sender@example.com',
	)
	def test_email_otp_can_be_verified_and_password_reset(self):
		user = User.objects.create_user(
			'reset-user',
			email='reset@example.com',
			password='old-password',
		)

		response = self.client.post(
			reverse('blog:forgot_password'),
			{'email': user.email},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(mail.outbox), 1)
		otp = self.client.session['reset_otp']
		self.assertIn(otp, mail.outbox[0].body)

		response = self.client.post(
			reverse('blog:verify_otp'),
			{'otp': otp},
		)
		self.assertContains(response, 'New Password')

		response = self.client.post(
			reverse('blog:reset_password'),
			{
				'password1': 'new-password-123',
				'password2': 'new-password-123',
			},
		)
		self.assertTrue(response.context['password_changed'])

		user.refresh_from_db()
		self.assertTrue(user.check_password('new-password-123'))


class CourseCreationPermissionTests(TestCase):
	def setUp(self):
		self.learner = User.objects.create_user('course-learner', password='pass')
		self.admin = User.objects.create_user(
			'course-admin',
			password='pass',
			is_staff=True,
		)

	def test_learner_cannot_open_or_submit_course_creation(self):
		self.client.force_login(self.learner)

		get_response = self.client.get(reverse('blog:create_post'))
		self.assertEqual(get_response.status_code, 403)
		self.assertNotContains(get_response, 'Create New Course', status_code=403)

		post_response = self.client.post(
			reverse('blog:create_post'),
			{'title': 'Unauthorized course', 'content': 'Attempted submission'},
		)
		self.assertEqual(post_response.status_code, 403)
		self.assertFalse(Post.objects.filter(title='Unauthorized course').exists())

		profile_response = self.client.get(reverse('blog:profile'))
		self.assertContains(profile_response, 'Courses')
		self.assertNotContains(profile_response, 'Create Course')

	def test_staff_user_can_open_and_create_course(self):
		self.client.force_login(self.admin)

		get_response = self.client.get(reverse('blog:create_post'))
		self.assertEqual(get_response.status_code, 200)
		self.assertContains(get_response, 'Create Course')

		post_response = self.client.post(
			reverse('blog:create_post'),
			{
				'title': 'Staff-created course',
				'content': 'Course content',
				'category': 'Python',
				'difficulty': 'Beginner',
			},
		)
		self.assertRedirects(post_response, reverse('blog:blogpage'))
		course = Post.objects.get(title='Staff-created course')
		self.assertEqual(course.author, self.admin)

		profile_response = self.client.get(reverse('blog:profile'))
		self.assertContains(profile_response, 'Create Course')

	def test_ask_community_link_uses_community_route(self):
		self.client.force_login(self.learner)

		response = self.client.get(reverse('blog:profile'))

		self.assertContains(
			response,
			'href="{}"'.format(reverse('blog:community')),
		)


class CoursePageTests(TestCase):
	def test_courses_page_renders(self):
		response = self.client.get(reverse('blog:blogpage'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'All topics')
		self.assertContains(response, 'images/vgrowhub-logo.svg')

	@override_settings(SITE_NAME='Test Brand')
	def test_site_name_is_shared_across_pages(self):
		login_response = self.client.get(reverse('blog:login'))
		courses_response = self.client.get(reverse('blog:blogpage'))
		self.assertContains(login_response, 'Test Brand')
		self.assertContains(courses_response, 'Courses | Test Brand')

	def test_course_card_destination_renders(self):
		author = User.objects.create_user('course-author', password='pass')
		viewer = User.objects.create_user('course-viewer', password='pass')
		course = Post.objects.create(
			title='Python Basics',
			content='Course introduction',
			author=author,
		)
		self.client.force_login(viewer)
		response = self.client.get(reverse('blog:post_detail', args=[course.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, course.title)
		self.assertEqual(reverse('blog:post_detail', args=[course.slug]),
			f'/course/{course.slug}/')
		self.assertRedirects(
			self.client.get(f'/course/{course.pk}/'),
			reverse('blog:post_detail', args=[course.slug]),
			status_code=301,
			fetch_redirect_response=False,
		)

	def test_course_comment_ajax_returns_json_without_redirect(self):
		author = User.objects.create_user('comment-course-author', password='pass')
		commenter = User.objects.create_user('commenter-user', password='pass')
		course = Post.objects.create(
			title='AJAX Comments',
			content='Course content',
			author=author,
		)
		self.client.force_login(commenter)

		response = self.client.post(
			reverse('blog:post_detail', args=[course.slug]),
			{'action': 'comment', 'content': '<script>hello</script>'},
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
			HTTP_ACCEPT='application/json',
		)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.json()['count'], 1)
		self.assertEqual(response.json()['comment']['content'], '<script>hello</script>')
		self.assertEqual(Comment.objects.filter(post=course, author=commenter).count(), 1)

	def test_course_comment_ajax_rejects_blank_comment(self):
		author = User.objects.create_user('comment-blank-author', password='pass')
		commenter = User.objects.create_user('comment-blank-user', password='pass')
		course = Post.objects.create(
			title='Blank Comment Course',
			content='Course content',
			author=author,
		)
		self.client.force_login(commenter)

		response = self.client.post(
			reverse('blog:post_detail', args=[course.slug]),
			{'action': 'comment', 'content': '   '},
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
			HTTP_ACCEPT='application/json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertFalse(Comment.objects.filter(post=course).exists())

	def test_lesson_slug_route_and_legacy_numeric_url(self):
		author = User.objects.create_user('lesson-author', password='pass')
		student = User.objects.create_user('lesson-student', password='pass')
		course = Post.objects.create(
			title='Python Course',
			content='Course content',
			author=author,
		)
		lesson = Lesson.objects.create(
			course=course,
			title='Functions in Python',
			content='Lesson body',
		)
		self.client.force_login(student)

		canonical_url = reverse('blog:lesson_detail', args=[lesson.slug])
		self.assertEqual(canonical_url, f'/lesson/{lesson.slug}/')
		self.assertEqual(self.client.get(canonical_url).status_code, 200)
		self.assertRedirects(
			self.client.get(f'/lesson/{lesson.pk}/'),
			canonical_url,
			status_code=301,
			fetch_redirect_response=False,
		)


class AssignmentAccessTests(TestCase):

	def setUp(self):
		self.admin = User.objects.create_user('admin', password='pass')
		self.student = User.objects.create_user('student', password='pass')
		self.other_student = User.objects.create_user('other', password='pass')
		self.course = Post.objects.create(
			title='Python',
			content='Course content',
			author=self.admin,
		)
		self.lesson = Lesson.objects.create(
			course=self.course,
			title='Functions',
			content='Lesson content',
		)

	def test_selected_standalone_assignment_is_private(self):
		assignment = Assignment.objects.create(
			title='Logic Test',
			description='Test',
			assignment_source='STANDALONE',
			status='PUBLISHED',
			created_by=self.admin,
		)
		AssignmentAudience.objects.create(
			assignment=assignment,
			audience_type='SELECTED_USER',
			user=self.student,
		)

		self.client.force_login(self.student)
		response = self.client.get(reverse('blog:assignments'))
		self.assertContains(response, 'Logic Test')

		self.client.force_login(self.other_student)
		response = self.client.get(reverse('blog:assignments'))
		self.assertNotContains(response, 'Logic Test')
		self.assertEqual(
			self.client.get(reverse('blog:assignment_attempt', args=[assignment.pk])).status_code,
			403,
		)

	def test_course_assignment_requires_enrollment(self):
		assignment = Assignment.objects.create(
			title='Functions Quiz',
			description='Test',
			assignment_source='COURSE',
			course=self.course,
			lesson=self.lesson,
			status='PUBLISHED',
			created_by=self.admin,
		)
		self.client.force_login(self.student)
		self.assertEqual(
			self.client.get(reverse('blog:assignment_attempt', args=[assignment.pk])).status_code,
			403,
		)

		Enrollment.objects.create(student=self.student, course=self.course)
		self.assertEqual(
			self.client.get(reverse('blog:assignment_attempt', args=[assignment.pk])).status_code,
			200,
		)

	def test_quiz_score_is_calculated_server_side(self):
		Enrollment.objects.create(student=self.student, course=self.course)
		assignment = Assignment.objects.create(
			title='Functions Quiz',
			description='Test',
			assignment_source='COURSE',
			assignment_type='QUIZ',
			course=self.course,
			lesson=self.lesson,
			status='PUBLISHED',
			max_score=1,
			passing_marks=1,
			created_by=self.admin,
		)
		question = AssignmentQuestion.objects.create(
			assignment=assignment,
			question='2 + 2?',
			marks=1,
		)
		correct = AssignmentOption.objects.create(
			question=question,
			option_text='4',
			is_correct=True,
		)
		AssignmentOption.objects.create(question=question, option_text='5')

		self.client.force_login(self.student)
		self.client.get(reverse('blog:assignment_attempt', args=[assignment.pk]))
		response = self.client.post(
			reverse('blog:assignment_attempt', args=[assignment.pk]),
			{'answer_data': '{"%s": ["%s"]}' % (question.pk, correct.pk)},
		)
		self.assertEqual(response.status_code, 302)
		attempt = AssignmentAttempt.objects.get(assignment=assignment, user=self.student)
		self.assertEqual(attempt.score, 1)
		self.assertTrue(attempt.passed)
		result_response = self.client.get(reverse('blog:assignment_attempt', args=[assignment.pk]))
		self.assertEqual(result_response.status_code, 200)
		self.assertContains(result_response, 'Score: 1 / 1')
		self.assertEqual(AssignmentAttempt.objects.filter(assignment=assignment, user=self.student).count(), 1)

	def test_text_submission_is_recorded_and_shown_for_manual_grading(self):
		Enrollment.objects.create(student=self.student, course=self.course)
		assignment = Assignment.objects.create(
			title='Explain Functions',
			description='Describe a function.',
			assignment_type='TEXT',
			course=self.course,
			status='PUBLISHED',
			created_by=self.admin,
		)
		self.client.force_login(self.student)
		self.client.get(reverse('blog:assignment_attempt', args=[assignment.pk]))
		response = self.client.post(
			reverse('blog:assignment_attempt', args=[assignment.pk]),
			{'answer_data': '{"response": "A reusable block of code."}'},
		)
		self.assertRedirects(response, reverse('blog:assignment_attempt', args=[assignment.pk]))
		submission = assignment.submissions.get(student=self.student)
		self.assertEqual(submission.answer, 'A reusable block of code.')
		result_response = self.client.get(reverse('blog:assignment_attempt', args=[assignment.pk]))
		self.assertContains(result_response, 'awaiting instructor review')
		self.assertContains(result_response, 'A reusable block of code.')

	def test_file_upload_can_be_graded_and_updates_progress(self):
		Enrollment.objects.create(student=self.student, course=self.course)
		assignment = Assignment.objects.create(
			title='Upload Work',
			description='Upload a file.',
			assignment_type='FILE_UPLOAD',
			course=self.course,
			status='PUBLISHED',
			max_score=10,
			passing_marks=6,
			created_by=self.admin,
		)
		self.client.force_login(self.student)
		self.client.get(reverse('blog:assignment_attempt', args=[assignment.pk]))
		response = self.client.post(
			reverse('blog:assignment_attempt', args=[assignment.pk]),
			{
				'answer_data': '{"response": "Completed file"}',
				'file': SimpleUploadedFile('work.txt', b'completed'),
			},
		)
		self.assertEqual(response.status_code, 302)
		submission = AssignmentSubmission.objects.get(assignment=assignment, student=self.student)
		self.assertTrue(submission.file.name.endswith('work.txt'))

		request = RequestFactory().post('/admin/blog/assignmentsubmission/')
		request.user = self.admin
		submission.score = 8
		submission.feedback = 'Good work.'
		AssignmentSubmissionAdmin(AssignmentSubmission, admin.site).save_model(
			request, submission, form=None, change=True
		)

		progress = assignment.progress_records.get(user=self.student)
		attempt = assignment.attempts.get(user=self.student)
		self.assertEqual(submission.status, 'Evaluated')
		self.assertEqual(attempt.status, 'EVALUATED')
		self.assertTrue(attempt.passed)
		self.assertEqual(attempt.feedback, 'Good work.')
		self.assertEqual(progress.status, 'PASSED')


class PracticeIntegrationTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user('practice-user', password='pass')
		self.client.force_login(self.user)

	def test_practice_page_uses_django_template(self):
		response = self.client.get(reverse('blog:practice'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Practice Arena')
		self.assertContains(response, 'practice_solver.css')
		self.assertContains(response, 'PRACTICE_STATE')

	def test_practice_subpages_render(self):
		for route_name in (
			'practice_details',
			'practice_all',
			'practice_playground',
			'practice_mock_tests',
			'practice_problem_sets',
			'practice_leaderboard',
		):
			with self.subTest(route=route_name):
				response = self.client.get(reverse(f'blog:{route_name}'))
				self.assertEqual(response.status_code, 200)

	def test_practice_tool_pages_load_consistent_theme_styles(self):
		expected_stylesheets = {
			'practice_playground': 'practice_playground.css?v=20261009-1',
			'practice_mock_tests': 'practice_subpages.css?v=20261009-1',
			'practice_problem_sets': 'practice_subpages.css?v=20261009-1',
			'practice_leaderboard': 'practice_leaderboard.css?v=20261009-1',
		}
		for route_name, stylesheet in expected_stylesheets.items():
			with self.subTest(route=route_name):
				response = self.client.get(reverse(f'blog:{route_name}'))
				self.assertEqual(response.status_code, 200)
				self.assertContains(response, stylesheet)

	def test_practice_draft_and_submission_are_persisted(self):
		draft_response = self.client.post(
			reverse('blog:practice_save_draft'),
			data={
				'problemId': 'two-sum',
				'language': 'python',
				'sourceCode': 'def two_sum(nums, target): return [0, 1]',
			},
			content_type='application/json',
		)
		self.assertEqual(draft_response.status_code, 200)
		progress = PracticeProgress.objects.get(user=self.user, problem__slug='two-sum')
		self.assertIn('python', progress.code_drafts)

		submit_response = self.client.post(
			reverse('blog:practice_record'),
			data={
				'kind': 'submit',
				'problemId': 'two-sum',
				'language': 'python',
				'sourceCode': 'def two_sum(nums, target): return [0, 1]',
				'status': 'ACCEPTED',
				'passed': 5,
				'total': 5,
			},
			content_type='application/json',
		)
		self.assertEqual(submit_response.status_code, 200)
		progress.refresh_from_db()
		self.assertEqual(progress.status, 'SOLVED')
		self.assertEqual(PracticeSubmission.objects.filter(user=self.user).count(), 1)


class AITutorPersistenceTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user('ai-tutor-user', password='pass')
		self.client.force_login(self.user)

	def mock_provider(self, answers):
		provider_patch = patch('blog.views.genai.Client')
		provider = provider_patch.start()
		self.addCleanup(provider_patch.stop)
		provider.return_value.models.generate_content.side_effect = [
			type('ProviderResponse', (), {'text': answer})()
			for answer in answers
		]
		return provider

	def send_question(self, question, conversation_id=''):
		data = {'question': question}
		if conversation_id:
			data['conversation_id'] = conversation_id
		return self.client.post(reverse('blog:ai_tutor'), data)

	def test_messages_are_persisted_and_followup_uses_conversation_context(self):
		provider = self.mock_provider(['First answer', 'Second answer'])
		first = self.send_question('First question')
		self.assertEqual(first.status_code, 200)
		conversation_id = first.json()['conversation_id']

		second = self.send_question('Follow-up question', str(conversation_id))
		self.assertEqual(second.status_code, 200)
		self.assertEqual(second.json()['conversation_id'], conversation_id)

		second_prompt = provider.return_value.models.generate_content.call_args_list[1].kwargs['contents']
		self.assertIn('First question', second_prompt)
		self.assertIn('First answer', second_prompt)
		self.assertIn('Follow-up question', second_prompt)
		self.assertEqual(AITutorMessage.objects.filter(conversation_id=conversation_id).count(), 4)

	def test_inactive_conversation_over_30_minutes_starts_a_new_chat(self):
		self.mock_provider(['First answer', 'Second answer'])
		first = self.send_question('First question')
		old_conversation = AITutorConversation.objects.get(pk=first.json()['conversation_id'])
		old_conversation.last_active_at = timezone.now() - timedelta(minutes=31)
		old_conversation.save(update_fields=['last_active_at'])

		second = self.send_question('New session question', str(old_conversation.pk))
		self.assertEqual(second.status_code, 200)
		self.assertNotEqual(second.json()['conversation_id'], old_conversation.pk)
		self.assertTrue(AITutorConversation.objects.filter(pk=old_conversation.pk).exists())

	def test_conversation_history_and_deletion_are_user_scoped(self):
		conversation = AITutorConversation.objects.create(
			user=self.user,
			title='Private title',
			last_active_at=timezone.now(),
		)
		AITutorMessage.objects.create(
			conversation=conversation,
			role='user',
			content='private search phrase',
		)
		AITutorMessage.objects.create(
			conversation=conversation,
			role='assistant',
			content='private reply',
		)
		history_item = self.client.get(
			reverse('blog:ai_tutor_history'),
			{'search': 'private search phrase'},
		).json()['items'][0]
		self.assertEqual(history_item['id'], conversation.pk)
		self.assertEqual(history_item['message_count'], 2)

		other_user = User.objects.create_user('other-ai-tutor-user', password='pass')
		self.client.force_login(other_user)
		url = reverse('blog:ai_tutor_conversation', args=[conversation.pk])
		self.assertEqual(self.client.get(url).status_code, 404)
		self.assertEqual(self.client.delete(url).status_code, 404)
		self.assertTrue(AITutorConversation.objects.filter(pk=conversation.pk).exists())

	def test_selecting_history_activates_owned_conversation(self):
		conversation = AITutorConversation.objects.create(
			user=self.user,
			title='Selected chat',
			last_active_at=timezone.now() - timedelta(minutes=5),
		)
		response = self.client.post(
			reverse('blog:ai_tutor_conversation', args=[conversation.pk]),
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()['conversation_id'], conversation.pk)
		self.assertEqual(
			self.client.session['ai_tutor_active_conversation_id'],
			conversation.pk,
		)
		conversation.refresh_from_db()
		self.assertLess(timezone.now() - conversation.last_active_at, timedelta(minutes=1))

	def test_tutor_page_renders_external_client_and_server_history(self):
		response = self.client.get(reverse('blog:ai_tutor'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "static/js/ai_tutor.js")
		self.assertContains(response, "Your conversations are saved to your account")

	def test_clear_history_deletes_only_the_signed_in_users_chats(self):
		conversation = AITutorConversation.objects.create(
			user=self.user,
			title='My chat',
			last_active_at=timezone.now(),
		)
		other_user = User.objects.create_user('another-tutor-user', password='pass')
		other_conversation = AITutorConversation.objects.create(
			user=other_user,
			title='Their chat',
			last_active_at=timezone.now(),
		)

		response = self.client.delete(reverse('blog:ai_tutor_clear_history'))

		self.assertEqual(response.status_code, 200)
		self.assertFalse(AITutorConversation.objects.filter(pk=conversation.pk).exists())
		self.assertTrue(AITutorConversation.objects.filter(pk=other_conversation.pk).exists())

	def test_provider_failure_is_reported_without_saving_a_conversation(self):
		provider = self.mock_provider([])
		provider.return_value.models.generate_content.side_effect = RuntimeError('provider unavailable')

		response = self.send_question('Question that fails')

		self.assertEqual(response.status_code, 502)
		self.assertIn('error', response.json())
		self.assertFalse(AITutorConversation.objects.filter(user=self.user).exists())


class CommunityWorkflowTests(TestCase):

	def setUp(self):
		self.author = User.objects.create_user('community-author', password='pass')
		self.learner = User.objects.create_user('community-learner', password='pass')
		self.post = CommunityPost.objects.create(
			author=self.author,
			title='How do Django forms validate?',
			category='Django',
			content='I need help understanding form validation.',
		)

	def test_community_and_create_question_require_authentication(self):
		self.assertRedirects(
			self.client.get(reverse('blog:community')),
			'/login/?next=/community/',
		)
		self.assertRedirects(
			self.client.get(reverse('blog:community_post_create')),
			'/login/?next=/community/create/',
		)

	def test_feed_search_topic_filter_empty_state_and_profile_link(self):
		self.client.force_login(self.learner)
		response = self.client.get(reverse('blog:community'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.post.title)
		self.assertContains(
			response,
			reverse('blog:user_profile', args=[self.author.username]),
		)

		response = self.client.get(
			reverse('blog:community'),
			{'q': 'forms', 'category': 'Django'},
		)
		self.assertContains(response, self.post.title)

		response = self.client.get(
			reverse('blog:community'),
			{'q': 'not-a-match'},
		)
		self.assertContains(response, 'No matching questions')
		self.assertContains(
			response,
			'href="{}"'.format(reverse('blog:community_post_create')),
		)

	def test_learner_can_create_and_read_a_community_question(self):
		self.client.force_login(self.learner)
		response = self.client.post(
			reverse('blog:community_post_create'),
			{
				'title': 'Why does my queryset return no rows?',
				'category': 'Python',
				'content': 'The filter works in the shell but not in the view.',
			},
		)

		created = CommunityPost.objects.get(
			title='Why does my queryset return no rows?',
		)
		self.assertEqual(created.author, self.learner)
		self.assertRedirects(
			response,
			reverse('blog:community_post_detail', args=[created.pk]),
		)
		detail = self.client.get(
			reverse('blog:community_post_detail', args=[created.pk]),
		)
		self.assertContains(detail, created.content)
		self.assertContains(detail, 'Write a reply')

	def test_like_save_and_reply_work_for_authenticated_users(self):
		self.client.force_login(self.learner)
		detail_url = reverse('blog:community_post_detail', args=[self.post.pk])

		self.assertRedirects(
			self.client.post(
				reverse('blog:community_post_like', args=[self.post.pk]),
			),
			detail_url,
		)
		self.assertTrue(self.post.liked_by.filter(pk=self.learner.pk).exists())
		self.client.post(reverse('blog:community_post_like', args=[self.post.pk]))
		self.assertFalse(self.post.liked_by.filter(pk=self.learner.pk).exists())

		self.client.post(reverse('blog:community_post_save', args=[self.post.pk]))
		self.assertTrue(self.post.saved_by.filter(pk=self.learner.pk).exists())

		reply_response = self.client.post(
			reverse('blog:community_reply_create', args=[self.post.pk]),
			{'content': 'Can you share the view and the exact form field?'},
		)
		self.assertRedirects(reply_response, detail_url)
		reply = CommunityReply.objects.get(post=self.post)
		self.assertEqual(reply.author, self.learner)
		self.assertEqual(
			Notification.objects.filter(
				recipient=self.author,
				sender=self.learner,
				notification_type='COMMUNITY_REPLY',
				community_post=self.post,
			).count(),
			1,
		)
		self.client.force_login(self.author)
		self.assertContains(
			self.client.get(reverse('blog:notifications')),
			'View question',
		)
		self.assertContains(self.client.get(detail_url), reply.content)

	def test_only_content_owners_can_edit_or_delete_posts_and_replies(self):
		self.client.force_login(self.learner)
		edit_url = reverse('blog:community_post_edit', args=[self.post.pk])
		delete_url = reverse('blog:community_post_delete', args=[self.post.pk])
		self.assertEqual(self.client.get(edit_url).status_code, 403)
		self.assertEqual(self.client.post(delete_url).status_code, 403)
		self.post.refresh_from_db()
		self.assertEqual(self.post.title, 'How do Django forms validate?')

		reply = CommunityReply.objects.create(
			post=self.post,
			author=self.author,
			content='Original answer',
		)
		self.assertEqual(
			self.client.post(
				reverse('blog:community_reply_delete', args=[reply.pk]),
			).status_code,
			403,
		)
		self.assertTrue(CommunityReply.objects.filter(pk=reply.pk).exists())
		self.assertEqual(
			self.client.get(
				reverse('blog:community_reply_edit', args=[reply.pk]),
			).status_code,
			403,
		)
		self.client.force_login(self.author)
		self.assertEqual(
			self.client.post(
				reverse('blog:community_reply_edit', args=[reply.pk]),
				{'content': 'Edited answer'},
			).status_code,
			302,
		)
		reply.refresh_from_db()
		self.assertEqual(reply.content, 'Edited answer')
		self.assertEqual(
			self.client.post(
				reverse('blog:community_reply_delete', args=[reply.pk]),
			).status_code,
			302,
		)
		self.assertFalse(CommunityReply.objects.filter(pk=reply.pk).exists())

		self.assertEqual(self.client.get(edit_url).status_code, 200)
		self.client.post(
			edit_url,
			{
				'title': 'Updated question title',
				'category': 'Django',
				'content': 'Updated question details',
			},
		)
		self.post.refresh_from_db()
		self.assertEqual(self.post.title, 'Updated question title')
		self.assertRedirects(
			self.client.post(delete_url),
			reverse('blog:community'),
		)
		self.assertFalse(CommunityPost.objects.filter(pk=self.post.pk).exists())
