from django.conf import settings
from django.contrib import admin
from django.contrib.auth.signals import user_logged_in
from django.core.management import call_command
from django.core.cache import cache
from django.contrib.auth.models import AnonymousUser, User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone
from allauth.account.models import EmailAddress
from types import SimpleNamespace
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from unittest.mock import patch
from io import BytesIO
from tempfile import TemporaryDirectory
from datetime import timedelta
import os
import uuid

from PIL import Image
from ai.services import ai_configuration

from .forms import EmailSignupForm
from .gmail_service import send_gmail
from myblog.adapters import VGrowHubSocialAccountAdapter
from .services.markdown import render_lesson_markdown
from .models import (
	Assignment,
	AssignmentAudience,
	AssignmentAttempt,
	AssignmentOption,
	AssignmentQuestion,
	AssignmentSubmission,
	FollowRequest,
	LoginHistory,
	Message,
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
	PracticeProblem,
	PracticeProblemSet,
	PlaygroundSession,
	PracticeSubmission,
	MockTest,
	MockTestAttempt,
	MockTestQuestion,
	XPEvent,
	UserProfile,
	UserSession,
	UserAssignmentProgress,
	SiteSettings,
)
from . import views
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
		self.assertContains(goal_page, 'Python Full Stack Developer')
		self.assertContains(goal_page, 'Django Developer')
		self.assertContains(goal_page, 'Data Analyst')
		self.assertContains(goal_page, 'Interview Prep')
		self.assertContains(goal_page, 'Web Basics')
		self.assertNotContains(goal_page, 'Other')

		response = self.client.post(
			reverse('blog:choose_goal'),
			{'goal': 'full_stack'},
		)
		self.assertRedirects(response, reverse('blog:dashboard'))
		user.profile_data.refresh_from_db()
		self.assertEqual(user.profile_data.goal, 'full_stack')
		self.assertTrue(user.profile_data.onboarding_completed)
		self.assertTemplateUsed(
			self.client.get(reverse('blog:dashboard')),
			'blog/dashboard.html',
		)

		self.client.post(reverse('blog:choose_goal'), {'goal': 'web'})
		user.profile_data.refresh_from_db()
		self.assertEqual(user.profile_data.goal, 'web')

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


class SocialAccountAdapterTests(TestCase):
	def test_google_username_uses_available_email_prefix(self):
		User.objects.create_user('weblays6', password='pass')
		sociallogin = SimpleNamespace(
			user=User(),
			account=SimpleNamespace(extra_data={}),
		)

		user = VGrowHubSocialAccountAdapter().populate_user(
			None,
			sociallogin,
			{'email': 'weblays6@gmail.com'},
		)

		self.assertEqual(user.username, 'weblays62')
		self.assertEqual(user.email, 'weblays6@gmail.com')


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

	@patch('blog.views.send_gmail', side_effect=RuntimeError('SMTP auth failed'))
	def test_forgot_password_email_failure_is_logged_and_reported(self, send_gmail):
		user = User.objects.create_user(
			'otp-failure-user',
			email='otp-failure@example.com',
			password='StrongPassword!123',
		)

		with self.assertLogs('blog.views', level='ERROR') as logs:
			response = self.client.post(
				reverse('blog:forgot_password'),
				{'email': user.email},
			)

		self.assertContains(response, "We couldn&#x27;t send the password reset email.")
		self.assertIn('SMTP auth failed', '\n'.join(logs.output))
		self.assertNotIn('reset_otp', self.client.session)
		send_gmail.assert_called_once()


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

	def test_people_page_shows_suggestions_without_a_search_query(self):
		response = self.client.get(reverse('blog:discover_users'))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['users'], [])
		self.assertContains(response, 'Suggested for you')

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
		self.assertEqual(email_args[1], 'Welcome to vGrowHub — Your account is ready 🎉')
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

	def test_private_follow_requests_wait_for_receiver_approval(self):
		self.owner.profile_data.is_private = True
		self.owner.profile_data.save(update_fields=['is_private'])
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

	def test_public_follow_is_immediate_and_duplicate_requests_are_prevented(self):
		self.client.force_login(self.viewer)
		first = self.client.post(
			reverse('blog:send_follow_request', args=[self.owner.username]),
		)
		self.assertEqual(first.status_code, 200)
		self.assertEqual(first.json()['status'], 'ACCEPTED')
		self.assertEqual(FollowRequest.objects.filter(
			sender=self.viewer,
			receiver=self.owner,
			status='ACCEPTED',
		).count(), 1)
		self.assertTrue(Notification.objects.filter(
			recipient=self.owner,
			sender=self.viewer,
			notification_type='NEW_FOLLOWER',
		).exists())
		duplicate = self.client.post(
			reverse('blog:send_follow_request', args=[self.owner.username]),
		)
		self.assertEqual(duplicate.status_code, 409)
		self.assertEqual(
			self.client.post(
				reverse('blog:send_follow_request', args=[self.viewer.username]),
			).status_code,
			400,
		)

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
			reverse('blog:follow_requests'),
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

	def test_unconnected_chat_creates_message_request_and_connected_chat_is_direct(self):
		self.client.force_login(self.viewer)

		response = self.client.get(reverse('blog:messages'))
		self.assertNotContains(response, 'privacy-owner')
		conversation_response = self.client.post(
			reverse('blog:start_personal_chat', args=[self.owner.username])
		)
		self.assertEqual(conversation_response.status_code, 403)

		FollowRequest.objects.create(
			sender=self.viewer,
			receiver=self.owner,
			status='ACCEPTED',
		)
		response = self.client.get(reverse('blog:messages'))
		self.assertEqual(response.status_code, 200)
		direct_chat = self.client.post(
			reverse('blog:start_personal_chat', args=[self.owner.username]),
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)
		self.assertEqual(direct_chat.status_code, 200)
		self.assertFalse(direct_chat.json()['is_request'])

	def test_allowed_non_follower_starts_one_message_request_and_can_be_accepted(self):
		self.owner.profile_data.who_can_message = 'everyone'
		self.owner.profile_data.save(update_fields=['who_can_message'])
		self.client.force_login(self.viewer)
		started = self.client.post(
			reverse('blog:start_personal_chat', args=[self.owner.username]),
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)
		self.assertEqual(started.status_code, 200)
		self.assertTrue(started.json()['is_request'])
		conversation = Conversation.objects.get(pk=started.json()['conversation_id'])
		response = self.client.post(
			started.json()['redirect_url'],
			{'content': 'Hello there'},
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(conversation.messages.count(), 1)
		self.assertTrue(Notification.objects.filter(
			recipient=self.owner,
			sender=self.viewer,
			notification_type='MESSAGE_REQUEST',
		).exists())
		another = self.client.post(
			started.json()['redirect_url'],
			{'content': 'One more'},
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)
		self.assertEqual(another.status_code, 409)
		recipient = Client()
		recipient.force_login(self.owner)
		accepted = recipient.post(
			reverse('blog:accept_message_request', args=[conversation.pk]),
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)
		self.assertEqual(accepted.status_code, 200)
		conversation.refresh_from_db()
		self.assertEqual(conversation.status, 'ACCEPTED')

	def test_blocked_user_cannot_start_message_request_when_everyone_is_allowed(self):
		self.owner.profile_data.who_can_message = 'everyone'
		self.owner.profile_data.save(update_fields=['who_can_message'])
		UserBlock.objects.create(blocker=self.owner, blocked=self.viewer)
		self.client.force_login(self.viewer)

		response = self.client.post(
			reverse('blog:start_personal_chat', args=[self.owner.username]),
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)

		self.assertEqual(response.status_code, 403)
		self.assertFalse(
			Conversation.objects.filter(
				project_owner=self.viewer,
				participant=self.owner,
			).exists()
			or Conversation.objects.filter(
				project_owner=self.owner,
				participant=self.viewer,
			).exists()
		)

	def test_new_message_search_includes_message_requests_and_one_way_connections(self):
		self.owner.profile_data.who_can_message = 'everyone'
		self.owner.profile_data.save(update_fields=['who_can_message'])
		self.client.force_login(self.viewer)

		response = self.client.get(reverse('blog:messages'))

		self.assertEqual(response.status_code, 200)
		self.assertIn(self.owner, response.context['available_users'])

		self.owner.profile_data.who_can_message = 'nobody'
		self.owner.profile_data.save(update_fields=['who_can_message'])
		FollowRequest.objects.create(
			sender=self.viewer,
			receiver=self.owner,
			status='ACCEPTED',
		)
		response = self.client.get(reverse('blog:messages'))
		self.assertIn(self.owner, response.context['available_users'])

	def test_private_follow_lists_require_approval_and_json_paginates(self):
		self.owner.profile_data.is_private = True
		self.owner.profile_data.save(update_fields=['is_private'])
		FollowRequest.objects.create(
			sender=self.viewer,
			receiver=self.owner,
			status='ACCEPTED',
		)
		self.client.force_login(self.viewer)

		following = self.client.get(
			reverse('blog:following_list', args=[self.viewer.username]),
			{'format': 'json', 'page': '1'},
		)
		self.assertEqual(following.status_code, 200)
		self.assertEqual(following.json()['count'], 1)
		self.assertEqual(following.json()['items'][0]['username'], self.owner.username)

		outsider = User.objects.create_user('private-list-outsider', password='pass')
		outsider_client = Client()
		outsider_client.force_login(outsider)
		self.assertEqual(
			outsider_client.get(
				reverse('blog:followers_list', args=[self.owner.username]),
			).status_code,
			404,
		)

	def test_rejecting_message_request_marks_its_notification_read(self):
		conversation = Conversation.objects.create(
			project_owner=self.viewer,
			participant=self.owner,
			status='REQUEST',
			request_sender=self.viewer,
		)
		Message.objects.create(
			conversation=conversation,
			sender=self.viewer,
			content='Please connect.',
		)
		notification = Notification.objects.create(
			recipient=self.owner,
			sender=self.viewer,
			notification_type='MESSAGE_REQUEST',
			message='A message request.',
		)
		self.client.force_login(self.owner)

		response = self.client.post(
			reverse('blog:reject_message_request', args=[conversation.pk]),
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)

		self.assertEqual(response.status_code, 200)
		self.assertFalse(Conversation.objects.filter(pk=conversation.pk).exists())
		notification.refresh_from_db()
		self.assertTrue(notification.is_read)

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


class PlatformFeatureTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user('platform-user', password='pass')
		self.other_user = User.objects.create_user('platform-other', password='pass')
		self.outsider = User.objects.create_user('platform-outsider', password='pass')

	def test_live_counts_require_login_and_only_count_the_current_user(self):
		Notification.objects.create(
			recipient=self.user,
			sender=self.other_user,
			notification_type='FOLLOW_REQUEST',
			message='A request for you.',
		)
		Notification.objects.create(
			recipient=self.other_user,
			sender=self.user,
			notification_type='FOLLOW_REQUEST',
			message='A request for someone else.',
		)
		FollowRequest.objects.create(
			sender=self.other_user,
			receiver=self.user,
			status='PENDING',
		)
		FollowRequest.objects.create(
			sender=self.user,
			receiver=self.other_user,
			status='PENDING',
		)
		user_conversation = Conversation.objects.create(
			project_owner=self.user,
			participant=self.other_user,
		)
		other_conversation = Conversation.objects.create(
			project_owner=self.other_user,
			participant=self.outsider,
		)
		Message.objects.create(
			conversation=user_conversation,
			sender=self.other_user,
			content='Unread for the current user.',
		)
		Message.objects.create(
			conversation=other_conversation,
			sender=self.outsider,
			content='Unread for the other user.',
		)

		url = reverse('blog:live_counts')
		self.assertEqual(self.client.get(url).status_code, 302)

		self.client.force_login(self.user)
		response = self.client.get(url)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), {
			'notifications_unread': 1,
			'messages_unread': 1,
			'follow_requests_pending': 1,
		})

	def test_free_and_premium_device_limits_and_oldest_session_revocation(self):
		first_client = Client()
		first_client.force_login(self.user)
		first_session_key = first_client.cookies[settings.SESSION_COOKIE_NAME].value

		second_client = Client()
		second_client.force_login(self.user)
		first_device = UserSession.objects.get(session_key=first_session_key)
		self.assertFalse(first_device.is_active)
		self.assertEqual(
			UserSession.objects.filter(user=self.user, is_active=True).count(),
			1,
		)

		profile = self.user.profile_data
		profile.plan = 'premium'
		profile.save(update_fields=['plan'])
		clients = [second_client]
		for _ in range(2):
			client = Client()
			client.force_login(self.user)
			clients.append(client)
		self.assertEqual(
			UserSession.objects.filter(user=self.user, is_active=True).count(),
			3,
		)

		newest_client = Client()
		newest_client.force_login(self.user)
		self.assertEqual(
			UserSession.objects.filter(user=self.user, is_active=True).count(),
			3,
		)
		first_device.refresh_from_db()
		self.assertFalse(first_device.is_active)
		self.assertFalse(
			UserSession.objects.filter(
				session_key=clients[0].cookies[settings.SESSION_COOKIE_NAME].value,
				is_active=True,
			).exists()
		)

	def test_revoked_session_is_rejected_on_its_next_request(self):
		old_client = Client()
		old_client.force_login(self.user)
		new_client = Client()
		new_client.force_login(self.user)

		response = old_client.get(reverse('blog:live_counts'))
		self.assertEqual(response.status_code, 401)
		self.assertEqual(response.json(), {'error': 'session_revoked'})

		html_old_client = Client()
		html_user = User.objects.create_user('revoked-html-user', password='pass')
		html_old_client.force_login(html_user)
		new_html_client = Client()
		new_html_client.force_login(html_user)
		response = html_old_client.get(reverse('blog:dashboard'))
		self.assertRedirects(
			response,
			f"{reverse('blog:login')}?device_signed_out=1",
			fetch_redirect_response=False,
		)
		response = html_old_client.get(response.url)
		self.assertEqual(response.status_code, 200)
		self.assertContains(
			response,
			'You were signed out because your account was used on another device.',
		)

	def test_sound_preferences_are_saved_and_login_history_is_limited(self):
		self.client.force_login(self.user)
		for _ in range(12):
			self.client.force_login(self.user)
		self.assertEqual(LoginHistory.objects.filter(user=self.user).count(), 10)

		response = self.client.post(
			reverse('blog:settings'),
			{
				'notification_sound': 'true',
				'message_sound': 'false',
			},
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)
		self.assertEqual(response.status_code, 200)
		self.user.profile_data.refresh_from_db()
		self.assertTrue(self.user.profile_data.notification_sound)
		self.assertFalse(self.user.profile_data.message_sound)
		self.assertEqual(response.json(), {
			'notification_sound': True,
			'message_sound': False,
		})

	def test_follow_request_navigation_and_notification_deep_links(self):
		types = (
			'FOLLOW_REQUEST',
			'FOLLOW_ACCEPTED',
			'FOLLOW_REJECTED',
			'FOLLOW_BACK',
			'COMMUNITY_REPLY',
			'NEW_FOLLOWER',
			'MESSAGE_REQUEST',
			'MESSAGE',
			'COURSE',
		)
		for notification_type in types:
			Notification.objects.create(
				recipient=self.user,
				sender=self.other_user,
				notification_type=notification_type,
				message=f'{notification_type} notification.',
			)

		self.client.force_login(self.user)
		follow_page = self.client.get(reverse('blog:follow_requests'))
		self.assertEqual(follow_page.status_code, 200)
		self.assertContains(follow_page, 'Follow Requests')
		self.assertContains(follow_page, reverse('blog:follow_requests'))
		self.assertContains(follow_page, 'class="nav-link active"')

		response = self.client.get(
			reverse('blog:notifications'),
			{'format': 'json', 'after': 0},
		)
		self.assertEqual(response.status_code, 200)
		items = response.json()['items']
		self.assertEqual(len(items), len(types))
		for item in items:
			with self.subTest(notification_type=item['notification_type']):
				self.assertEqual(self.client.get(item['url']).status_code, 200)
		follow_item = next(
			item for item in items
			if item['notification_type'] == 'FOLLOW_REQUEST'
		)
		self.assertEqual(
			follow_item['url'],
			reverse('blog:follow_requests'),
		)
		marked = self.client.post(
			f"{reverse('blog:notifications')}?format=json",
			{'notification_id': follow_item['id']},
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
		)
		self.assertEqual(marked.status_code, 200)
		self.assertTrue(
			Notification.objects.get(pk=follow_item['id']).is_read
		)

	def test_user_cannot_revoke_another_users_device(self):
		other_client = Client()
		other_client.force_login(self.other_user)
		other_session_key = other_client.cookies[
			settings.SESSION_COOKIE_NAME
		].value
		other_device = UserSession.objects.get(session_key=other_session_key)
		self.client.force_login(self.user)

		response = self.client.post(
			reverse('blog:revoke_device_session', args=[other_device.id]),
		)

		self.assertEqual(response.status_code, 404)
		other_device.refresh_from_db()
		self.assertTrue(other_device.is_active)

	@override_settings(DEBUG=False)
	def test_custom_not_found_page_uses_the_shared_base_template(self):
		response = self.client.get('/missing-platform-page/')

		self.assertEqual(response.status_code, 404)
		self.assertTemplateUsed(response, 'blog/404.html')
		self.assertContains(response, 'Page not found', status_code=404)

	def test_custom_server_error_page_uses_the_shared_base_template(self):
		request = RequestFactory().get('/failure/')
		request.user = AnonymousUser()
		request.resolver_match = resolve(reverse('blog:login'))
		response = views.custom_500(request)

		self.assertEqual(response.status_code, 500)
		self.assertIn(b'Something went wrong', response.content)

	def test_service_worker_is_root_scoped_and_limits_caching_to_static_assets(self):
		response = self.client.get(reverse('blog:service_worker'))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response['Service-Worker-Allowed'], '/')
		self.assertIn('application/javascript', response['Content-Type'])
		worker = response.content.decode()
		self.assertIn("url.pathname.startsWith('/static/')", worker)
		self.assertIn("request.method !== 'GET'", worker)
		self.assertNotIn("caches.put(request, response)", worker)


class ConversationWebSocketTests(TransactionTestCase):
	def setUp(self):
		self.sender = User.objects.create_user('socket-sender', password='pass')
		self.receiver = User.objects.create_user('socket-receiver', password='pass')
		self.conversation = Conversation.objects.create(
			project_owner=self.sender,
			participant=self.receiver,
		)

	def test_personal_websocket_rejects_non_mutual_followers(self):
		FollowRequest.objects.create(
			sender=self.sender,
			receiver=self.receiver,
			status='ACCEPTED',
		)
		communicator = WebsocketCommunicator(
			ConversationConsumer.as_asgi(),
			f'/ws/messages/{self.conversation.id}/',
		)
		communicator.scope['user'] = self.sender
		communicator.scope['url_route'] = {
			'kwargs': {'conversation_id': self.conversation.id},
		}

		connected, close_code = async_to_sync(communicator.connect)()

		self.assertFalse(connected)
		self.assertEqual(close_code, 4403)

	def test_deactivated_account_cannot_subscribe_to_websocket(self):
		self.sender.profile_data.is_deactivated = True
		self.sender.profile_data.save(update_fields=['is_deactivated'])
		communicator = WebsocketCommunicator(
			ConversationConsumer.as_asgi(),
			f'/ws/messages/{self.conversation.id}/',
		)
		communicator.scope['user'] = self.sender
		communicator.scope['url_route'] = {
			'kwargs': {'conversation_id': self.conversation.id},
		}

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
		communicator = WebsocketCommunicator(
			ConversationConsumer.as_asgi(),
			f'/ws/messages/{self.conversation.id}/',
		)
		communicator.scope['user'] = self.sender
		communicator.scope['url_route'] = {
			'kwargs': {'conversation_id': self.conversation.id},
		}

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
		DEFAULT_FROM_EMAIL='vGrowHub <sender@example.com>',
	)
	def test_allauth_password_reset_uses_configured_django_mail_backend(self):
		user = User.objects.create_user(
			'allauth-reset-user',
			email='allauth-reset@example.com',
			password='StrongPassword!123',
		)
		EmailAddress.objects.create(
			user=user,
			email=user.email,
			primary=True,
			verified=True,
		)

		response = self.client.post(
			reverse('account_reset_password'),
			{'email': user.email},
		)

		self.assertRedirects(response, reverse('account_reset_password_done'))
		self.assertEqual(len(mail.outbox), 1)
		self.assertEqual(mail.outbox[0].from_email, 'vGrowHub <sender@example.com>')
		self.assertEqual(mail.outbox[0].to, [user.email])

	@override_settings(
		EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
		EMAIL_HOST_USER='sender@example.com',
		EMAIL_HOST_PASSWORD='test-password',
		DEFAULT_FROM_EMAIL='vGrowHub <sender@example.com>',
	)
	@patch(
		'django.core.mail.backends.locmem.EmailBackend.send_messages',
		side_effect=RuntimeError('SMTP auth failed'),
	)
	def test_allauth_password_reset_failure_is_logged_and_reported(self, send_messages):
		user = User.objects.create_user(
			'allauth-reset-failure-user',
			email='allauth-reset-failure@example.com',
			password='StrongPassword!123',
		)
		EmailAddress.objects.create(
			user=user,
			email=user.email,
			primary=True,
			verified=True,
		)

		with self.assertLogs('myblog.adapters', level='ERROR') as logs:
			response = self.client.post(
				reverse('account_reset_password'),
				{'email': user.email},
				follow=True,
			)

		self.assertContains(response, "We couldn&#x27;t send the email. Please try again later.")
		self.assertIn('SMTP auth failed', '\n'.join(logs.output))
		send_messages.assert_called_once()

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
		self.assertEqual(reverse('blog:course_detail', args=[course.slug]),
			f'/courses/{course.slug}/')
		self.assertEqual(
			self.client.get(reverse('blog:course_detail', args=[course.slug])).status_code,
			200,
		)
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
		Enrollment.objects.create(student=student, course=course)
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
		response = self.client.get(reverse('blog:assignments'), {'tab': 'extra'})
		self.assertContains(response, 'Logic Test')

		self.client.force_login(self.other_student)
		response = self.client.get(reverse('blog:assignments'), {'tab': 'extra'})
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

	def test_default_assignment_tab_only_shows_enrolled_course_assignments(self):
		course_assignment = Assignment.objects.create(
			title='Enrolled Course Work',
			description='Course assignment',
			assignment_source='COURSE',
			course=self.course,
			status='PUBLISHED',
			created_by=self.admin,
		)
		extra_assignment = Assignment.objects.create(
			title='Optional Standalone Work',
			description='Extra practice',
			assignment_source='STANDALONE',
			status='PUBLISHED',
			created_by=self.admin,
		)
		AssignmentAudience.objects.create(assignment=extra_assignment, audience_type='ALL_USERS')
		Enrollment.objects.create(student=self.student, course=self.course)
		self.client.force_login(self.student)

		response = self.client.get(reverse('blog:assignments'))
		self.assertContains(response, course_assignment.title)
		self.assertNotContains(response, extra_assignment.title)
		self.assertEqual(response.context['active_tab'], 'courses')

		response = self.client.get(reverse('blog:assignments'), {'tab': 'extra'})
		self.assertContains(response, extra_assignment.title)
		self.assertNotContains(response, course_assignment.title)

	def test_assignment_list_paginates_eight_items_and_preserves_tab(self):
		Enrollment.objects.create(student=self.student, course=self.course)
		for index in range(10):
			Assignment.objects.create(
				title=f'Course Task {index}',
				description='Course assignment',
				assignment_source='COURSE',
				course=self.course,
				status='PUBLISHED',
				created_by=self.admin,
			)
		self.client.force_login(self.student)

		first_page = self.client.get(reverse('blog:assignments'))
		self.assertEqual(first_page.context['page_obj'].paginator.count, 10)
		self.assertEqual(len(first_page.context['assignments']), 8)
		self.assertContains(first_page, 'Page 1 of 2')
		self.assertContains(first_page, 'tab=courses')
		self.assertContains(first_page, 'page=2')

		second_page = self.client.get(reverse('blog:assignments'), {'tab': 'courses', 'page': 2})
		self.assertEqual(len(second_page.context['assignments']), 2)

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

	def test_invalid_upload_type_is_rejected(self):
		Enrollment.objects.create(student=self.student, course=self.course)
		assignment = Assignment.objects.create(
			title='Upload Work',
			description='Upload a file.',
			assignment_type='FILE_UPLOAD',
			course=self.course,
			status='PUBLISHED',
			created_by=self.admin,
		)
		self.client.force_login(self.student)
		self.client.get(reverse('blog:assignment_attempt', args=[assignment.pk]))
		response = self.client.post(
			reverse('blog:assignment_attempt', args=[assignment.pk]),
			{
				'answer_data': '{"response": "completed"}',
				'file': SimpleUploadedFile('malware.exe', b'not executable'),
			},
		)
		self.assertEqual(response.status_code, 400)
		self.assertFalse(AssignmentSubmission.objects.filter(assignment=assignment, student=self.student).exists())

	def test_submission_can_be_resubmitted_before_deadline(self):
		Enrollment.objects.create(student=self.student, course=self.course)
		assignment = Assignment.objects.create(
			title='Resubmittable Work',
			description='Submit, then improve your answer.',
			assignment_type='TEXT',
			course=self.course,
			status='PUBLISHED',
			due_date=timezone.now() + timedelta(days=1),
			max_attempts=1,
			created_by=self.admin,
		)
		self.client.force_login(self.student)
		url = reverse('blog:assignment_attempt', args=[assignment.pk])
		self.client.get(url)
		self.client.post(url, {'answer_data': '{"response": "first version"}'})
		self.client.get(url + '?new=1')
		response = self.client.post(url, {'answer_data': '{"response": "improved version"}'})
		self.assertEqual(response.status_code, 302)
		self.assertEqual(AssignmentSubmission.objects.filter(assignment=assignment, student=self.student).count(), 2)


class AssignmentWorkflowEnhancementTests(TestCase):

	def setUp(self):
		self.staff = User.objects.create_user('assignment-staff', password='pass', is_staff=True)
		self.student = User.objects.create_user('assignment-student', password='pass')
		self.assignment = Assignment.objects.create(
			title='Late rubric assignment',
			description='Test the grading flow.',
			assignment_source='STANDALONE',
			assignment_type='TEXT',
			status='PUBLISHED',
			created_by=self.staff,
			due_date=timezone.now() - timedelta(days=1),
			late_submission_allowed=True,
			late_penalty_percent=20,
			max_score=100,
			rubric=[{'name': 'Completeness', 'points': 80}, {'name': 'Clarity', 'points': 20}],
		)
		AssignmentAudience.objects.create(
			assignment=self.assignment,
			audience_type='SELECTED_USER',
			user=self.student,
		)
		self.submission = AssignmentSubmission.objects.create(
			assignment=self.assignment,
			student=self.student,
			answer='My work.',
		)

	def test_staff_only_evaluation_applies_late_penalty_and_notifies_once(self):
		url = reverse('blog:assignment_evaluate', args=[self.assignment.pk])
		self.client.force_login(self.student)
		self.assertEqual(self.client.get(url).status_code, 403)

		self.client.force_login(self.staff)
		response = self.client.post(url, {
			'action': 'publish',
			'submission_ids': [self.submission.pk],
			f'score_{self.submission.pk}': '80',
			f'rubric_{self.submission.pk}': '{"Completeness": 70, "Clarity": 10}',
			f'feedback_{self.submission.pk}': 'Good work.',
		})
		self.assertEqual(response.status_code, 302)
		self.submission.refresh_from_db()
		self.assertEqual(self.submission.score, 64)
		self.assertTrue(self.submission.is_late)
		self.assertEqual(self.submission.rubric_feedback, {'Completeness': 70, 'Clarity': 10})
		self.assertEqual(Notification.objects.filter(
			recipient=self.student,
			notification_type='ASSIGNMENT_EVALUATED',
			dedupe_key=f'assignment-evaluated:{self.submission.pk}',
		).count(), 1)
		self.client.post(url, {
			'action': 'publish',
			'submission_ids': [self.submission.pk],
			f'rubric_{self.submission.pk}': '{"Completeness": 70, "Clarity": 10}',
		})
		self.assertEqual(Notification.objects.filter(
			recipient=self.student,
			notification_type='ASSIGNMENT_EVALUATED',
			dedupe_key=f'assignment-evaluated:{self.submission.pk}',
		).count(), 1)

	def test_score_math_and_past_due_filter(self):
		UserAssignmentProgress.objects.create(
			user=self.student,
			assignment=self.assignment,
			status='NOT_STARTED',
			best_score=64,
		)
		self.client.force_login(self.student)
		scores = self.client.get(reverse('blog:assignment_scores'))
		self.assertEqual(scores.status_code, 200)
		self.assertContains(scores, '64')
		past_due = self.client.get(reverse('blog:assignments'), {'tab': 'extra', 'status': 'past_due'})
		self.assertEqual(past_due.status_code, 200)
		self.assertContains(past_due, 'Past Due')
		self.assertContains(past_due, 'Late rubric assignment')

	def test_assignment_seed_command_is_idempotent(self):
		call_command('seed_assignments')
		first_count = Assignment.objects.filter(title__in=[
			'Build a Personal Portfolio',
			'Python Data Cleanup',
			'SQL Reporting Queries',
			'Django Notes App',
			'JavaScript Interactive Form',
		]).count()
		call_command('seed_assignments')
		second_count = Assignment.objects.filter(title__in=[
			'Build a Personal Portfolio',
			'Python Data Cleanup',
			'SQL Reporting Queries',
			'Django Notes App',
			'JavaScript Interactive Form',
		]).count()
		self.assertEqual(first_count, 5)
		self.assertEqual(second_count, 5)

	def test_due_reminder_command_is_idempotent(self):
		assignment = Assignment.objects.create(
			title='Due soon assignment',
			description='Reminder test.',
			assignment_source='STANDALONE',
			status='PUBLISHED',
			created_by=self.staff,
			due_date=timezone.now() + timedelta(hours=2),
		)
		AssignmentAudience.objects.create(assignment=assignment, audience_type='ALL_USERS')
		call_command('send_due_reminders')
		call_command('send_due_reminders')
		self.assertEqual(Notification.objects.filter(
			recipient=self.student,
			notification_type='ASSIGNMENT_DUE',
			dedupe_key=f'assignment-due:{assignment.pk}:{self.student.pk}',
		).count(), 1)


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

	def test_practice_draft_and_submission_are_persisted(self):
		self.create_problem('two-sum')
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

	def create_problem(self, slug='practice-test-problem'):
		return PracticeProblem.objects.create(
			slug=slug,
			title='Practice test problem',
			description='A test exercise.',
			difficulty='EASY',
			category='python',
			function_name='solve',
			starter_code={'python': 'def solve(value): return value'},
			public_tests=[{'input': [1], 'expected': 1}],
			hidden_tests=[{'input': [2], 'expected': 2}],
			hints=['First hint', 'Second hint'],
			editorial='Private solution details',
		)

	def test_submission_awards_xp_only_on_first_client_verified_solve(self):
		problem = self.create_problem()
		payload = {
			'kind': 'submit',
			'problemId': problem.slug,
			'language': 'python',
			'sourceCode': 'def solve(value): return value',
			'status': 'ACCEPTED',
			'passed': 2,
			'total': 2,
		}
		for _ in range(2):
			response = self.client.post(
				reverse('blog:practice_record'),
				data=payload,
				content_type='application/json',
			)
			self.assertEqual(response.status_code, 200)
		self.assertEqual(
			PracticeSubmission.objects.filter(user=self.user, client_verified=True).count(),
			2,
		)
		self.assertEqual(
			XPEvent.objects.filter(
				user=self.user,
				event_type='FIRST_PROBLEM_SOLVE',
				source_type='practice_problem',
				source_id=str(problem.pk),
			).count(),
			1,
		)

	def test_problem_editorial_unlocks_after_three_attempts_and_notes_are_private(self):
		problem = self.create_problem()
		url = reverse('blog:practice_problem_detail', kwargs={'slug': problem.slug})
		response = self.client.get(url)
		self.assertContains(response, 'Solution unlocks after three attempts')
		self.assertNotContains(response, 'Private solution details')
		PracticeProgress.objects.create(user=self.user, problem=problem, attempt_count=3, notes='My private note')
		response = self.client.get(url)
		self.assertContains(response, 'Private solution details')
		self.assertContains(response, 'My private note')
		other = User.objects.create_user('practice-other-user', password='pass')
		self.client.force_login(other)
		response = self.client.get(url)
		self.assertNotContains(response, 'My private note')

	def test_playground_sessions_are_owner_scoped_and_share_links_are_revocable(self):
		owner = PlaygroundSession.objects.create(
			user=self.user,
			title='Owner workspace',
			language='python',
			source_code='print(1)',
		)
		other = User.objects.create_user('practice-session-owner', password='pass')
		self.client.force_login(other)
		action_url = reverse('blog:playground_session_action', args=(owner.pk,))
		response = self.client.post(
			action_url,
			data={'action': 'share'},
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 404)
		self.client.force_login(self.user)
		response = self.client.post(
			action_url,
			data={'action': 'share'},
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 200)
		owner.refresh_from_db()
		self.assertEqual(
			self.client.get(reverse('blog:playground_share', args=(owner.share_token,))).status_code,
			200,
		)
		self.client.post(
			action_url,
			data={'action': 'revoke'},
			content_type='application/json',
		)
		owner.refresh_from_db()
		self.assertIsNone(owner.share_token)
		self.assertEqual(
			self.client.get(reverse('blog:playground_share', args=(owner.share_token or '00000000-0000-0000-0000-000000000000',))).status_code,
			404,
		)

	def test_mock_test_scoring_and_server_expiry(self):
		test = MockTest.objects.create(
			title='Timed test',
			slug='timed-test',
			description='Test server timing.',
			duration_minutes=1,
			active=True,
		)
		question = MockTestQuestion.objects.create(
			test=test,
			prompt='Choose the correct answer.',
			options=[{'id': 'a', 'text': 'Correct'}, {'id': 'b', 'text': 'Incorrect'}],
			correct_answer='a',
			points=5,
			order=1,
		)
		start = self.client.post(reverse('blog:practice_mock_test_start', args=(test.pk,)))
		self.assertEqual(start.status_code, 302)
		attempt = MockTestAttempt.objects.get(user=self.user, test=test)
		answer_url = reverse('blog:practice_mock_test_answer', args=(attempt.pk,))
		answer = self.client.post(
			answer_url,
			data={'questionId': question.pk, 'answer': 'a'},
			content_type='application/json',
		)
		self.assertEqual(answer.status_code, 200)
		attempt.expires_at = timezone.now() - timedelta(seconds=1)
		attempt.save(update_fields=['expires_at'])
		response = self.client.post(reverse('blog:practice_mock_test_submit', args=(attempt.pk,)))
		self.assertEqual(response.status_code, 302)
		attempt.refresh_from_db()
		self.assertEqual(attempt.status, 'EXPIRED')
		self.assertEqual(attempt.score, 5)
		self.assertEqual(attempt.total_score, 5)

	def test_problem_seed_command_is_idempotent(self):
		call_command('seed_problems', verbosity=0)
		call_command('seed_problems', verbosity=0)
		self.assertEqual(PracticeProblem.objects.count(), 30)
		self.assertEqual(PracticeProblemSet.objects.count(), 3)
		for problem in PracticeProblem.objects.all():
			self.assertEqual(len(problem.public_tests), 3)
			self.assertEqual(len(problem.hidden_tests), 3)
			expected_language = {
				'python': 'python',
				'javascript': 'javascript',
				'sql': 'sql',
				'html-css': 'html',
				'django': 'python',
			}[problem.category]
			self.assertIn(expected_language, problem.starter_code)
		self.assertEqual(
			PracticeProblemSet.objects.get(slug='interview-50').problems.count(),
			30,
		)


class AITutorPersistenceTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user('ai-tutor-user', password='pass')
		self.client.force_login(self.user)
		cache.delete('blog.site_settings')
		cache.delete(f'ai-tutor-minute:{self.user.pk}')
		environment_patch = patch.dict(os.environ, {
			'AI_PROVIDER': 'gemini',
			'AI_API_KEY': 'test-key',
			'AI_MODEL_FAST': 'test-model-fast',
			'AI_MODEL_BALANCED': 'test-model-balanced',
			'AI_MODEL_DEEP': 'test-model-deep',
		})
		environment_patch.start()
		self.addCleanup(environment_patch.stop)

	def mock_provider(self, answers):
		provider_patch = patch('blog.views.stream_chat')
		provider = provider_patch.start()
		self.addCleanup(provider_patch.stop)
		provider.side_effect = [iter([answer]) for answer in answers]
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

		second_prompt = provider.call_args_list[1].args[0]
		self.assertIn('First question', [message['content'] for message in second_prompt])
		self.assertIn('First answer', [message['content'] for message in second_prompt])
		self.assertIn('Follow-up question', [message['content'] for message in second_prompt])
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
		self.assertContains(response, "static/css/ai_tutor_workspace.css")
		self.assertContains(response, "Your conversations are saved to your account")
		self.assertContains(response, "ai-empty-state")
		self.assertContains(response, "ai-slash-menu")
		self.assertContains(response, "ai-sidebar-search")
		self.assertContains(response, 'id="sidebarToggle"')
		self.assertContains(response, 'id="aiSidebarClose"')
		self.assertContains(response, 'id="aiSidebarBackdrop"')
		self.assertContains(response, "<span>Back to vGrowHub</span>")
		self.assertContains(response, 'href="{}"'.format(reverse('blog:dashboard')))
		self.assertContains(response, "ai-char-count")

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
		provider.side_effect = RuntimeError('provider unavailable')

		response = self.send_question('Question that fails')

		self.assertEqual(response.status_code, 502)
		self.assertIn('error', response.json())
		self.assertFalse(AITutorConversation.objects.filter(user=self.user).exists())

	def test_streaming_response_persists_the_assistant_reply(self):
		self.mock_provider(['A streamed answer.'])
		response = self.client.post(reverse('blog:ai_tutor'), {
			'question': 'Explain streaming.',
			'stream': '1',
		})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response['Content-Type'], 'text/event-stream')
		stream = b''.join(response.streaming_content).decode()
		self.assertIn('event: token', stream)
		self.assertIn('event: done', stream)
		conversation = AITutorConversation.objects.get(user=self.user)
		self.assertEqual(list(conversation.messages.values_list('content', flat=True)), ['Explain streaming.', 'A streamed answer.'])

	def test_attachment_extension_and_size_are_validated(self):
		response = self.client.post(reverse('blog:ai_tutor'), {
			'question': 'Review this attachment.',
			'attachment': SimpleUploadedFile('payload.exe', b'not text'),
		})
		self.assertEqual(response.status_code, 400)
		response = self.client.post(reverse('blog:ai_tutor'), {
			'question': 'Review this attachment.',
			'attachment': SimpleUploadedFile('large.py', b'x' * (200 * 1024 + 1)),
		})
		self.assertEqual(response.status_code, 400)

	def test_share_link_can_be_revoked(self):
		conversation = AITutorConversation.objects.create(
			user=self.user,
			title='Shareable chat',
			last_active_at=timezone.now(),
		)
		token = uuid.uuid4()
		conversation.share_token = token
		conversation.save(update_fields=['share_token'])
		response = self.client.post(
			reverse('blog:ai_tutor_conversation_action', args=[conversation.pk]),
			{'action': 'revoke'},
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.client.get(reverse('blog:ai_tutor_share', args=[token])).status_code, 404)

	def test_editing_last_message_replaces_the_previous_reply(self):
		self.mock_provider(['Original answer.', 'Revised answer.'])
		first = self.send_question('Original question')
		conversation_id = first.json()['conversation_id']
		user_message = AITutorMessage.objects.get(conversation_id=conversation_id, role='user')
		response = self.client.post(reverse('blog:ai_tutor'), {
			'question': 'Edited question',
			'conversation_id': conversation_id,
			'edit_message_id': user_message.pk,
		})
		self.assertEqual(response.status_code, 200)
		messages = list(AITutorMessage.objects.filter(conversation_id=conversation_id).order_by('id'))
		self.assertEqual([message.content for message in messages], ['Edited question', 'Revised answer.'])

	def test_daily_message_limit_is_enforced(self):
		settings_row = SiteSettings.get_cached()
		settings_row.ai_daily_limit_free = 1
		settings_row.save()
		self.mock_provider(['One reply.'])
		self.assertEqual(self.send_question('First').status_code, 200)
		response = self.send_question('Second')
		self.assertEqual(response.status_code, 429)

	def test_missing_model_configuration_returns_a_friendly_error(self):
		with patch.dict(os.environ, {'AI_MODEL_BALANCED': ''}):
			response = self.send_question('Hello')
		self.assertEqual(response.status_code, 503)
		self.assertIn('not configured', response.json()['error'])

	def test_ai_environment_configuration_supports_primary_and_legacy_keys(self):
		with patch.dict(os.environ, {'AI_PROVIDER': 'google', 'AI_API_KEY': 'primary-key'}):
			configuration = ai_configuration()
		self.assertTrue(configuration['configured'])
		self.assertEqual(configuration['api_key'], 'primary-key')
		self.assertEqual(configuration['provider'], 'google')

		with patch.dict(os.environ, {'AI_API_KEY': '', 'GEMINI_API_KEY': 'legacy-key'}):
			configuration = ai_configuration()
		self.assertTrue(configuration['configured'])
		self.assertEqual(configuration['api_key'], 'legacy-key')

	def test_missing_configuration_shows_calm_user_notice_and_admin_setup_card(self):
		missing = {
			'AI_API_KEY': '',
			'GEMINI_API_KEY': '',
			'AI_MODEL_BALANCED': '',
		}
		with patch.dict(os.environ, missing):
			user_response = self.client.get(reverse('blog:ai_tutor'))
			self.assertContains(user_response, 'AI is offline right now')
			self.assertNotContains(user_response, 'AI Tutor setup needed')

			admin_user = User.objects.create_user('ai-tutor-admin', password='pass', is_staff=True)
			self.client.force_login(admin_user)
			admin_response = self.client.get(reverse('blog:ai_tutor'))
			self.assertContains(admin_response, 'AI Tutor setup needed')
			self.assertContains(admin_response, 'AI_API_KEY')

	def test_slash_commands_select_server_side_mode(self):
		provider = self.mock_provider(['Debugging explanation.'])
		response = self.send_question('/debug The app returns a 500.')

		self.assertEqual(response.status_code, 200)
		self.assertIn('Help debug', provider.call_args.kwargs['system_prompt'])
		self.assertEqual(provider.call_args.args[0][-1]['content'], 'The app returns a 500.')

	def test_lesson_context_can_be_cleared_without_deleting_chat(self):
		conversation = AITutorConversation.objects.create(
			user=self.user,
			title='Keep this chat',
			last_active_at=timezone.now(),
		)
		session = self.client.session
		session['ai_tutor_lesson_context'] = {'slug': 'functions', 'title': 'Functions', 'content': 'Lesson'}
		session['ai_tutor_external_context'] = 'private context'
		session.save()

		response = self.client.post(reverse('blog:ai_tutor_clear_context'))

		self.assertEqual(response.status_code, 200)
		self.assertTrue(AITutorConversation.objects.filter(pk=conversation.pk).exists())
		self.assertNotIn('ai_tutor_lesson_context', self.client.session)
		self.assertNotIn('ai_tutor_external_context', self.client.session)

	def test_per_minute_limit_and_streaming_authentication(self):
		key = f'ai-tutor-minute:{self.user.pk}'
		cache.delete(key)
		for _ in range(11):
			views._ai_rate_limited(self.user)
		response = self.send_question('Rate-limited')
		self.assertEqual(response.status_code, 429)
		anonymous = Client()
		response = anonymous.post(reverse('blog:ai_tutor'), {'question': 'Unauthenticated', 'stream': '1'})
		self.assertIn(response.status_code, (302, 401))

	def test_markdown_renderer_escapes_script_markup(self):
		rendered = str(render_lesson_markdown('<script>alert("x")</script>'))
		self.assertNotIn('<script>', rendered)
		self.assertIn('&lt;script&gt;', rendered)


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


from tests.test_smoke import ScopedPageSmokeTests
from tests.test_dashboard_gamification import XPAwardTests
