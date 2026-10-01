from django.contrib import admin
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .models import (
	Assignment,
	AssignmentAudience,
	AssignmentAttempt,
	AssignmentOption,
	AssignmentQuestion,
	AssignmentSubmission,
	Enrollment,
	Lesson,
	Post,
	PracticeProgress,
	PracticeSubmission,
)
from .admin import AssignmentSubmissionAdmin


class HomeRedirectTests(TestCase):
	def test_anonymous_user_sees_login_page(self):
		response = self.client.get(reverse('blog:home'))
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'blog/login.html')

	def test_authenticated_user_is_sent_to_dashboard(self):
		user = User.objects.create_user('home-user', password='pass')
		self.client.force_login(user)
		response = self.client.get(reverse('blog:home'))
		self.assertRedirects(response, reverse('blog:dashboard'), fetch_redirect_response=False)


class CoursePageTests(TestCase):
	def test_courses_page_renders(self):
		response = self.client.get(reverse('blog:blogpage'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'All topics')
		self.assertContains(response, 'images/vgrowhub-logo.svg')

	@override_settings(SITE_NAME='Test Brand')
	def test_site_name_is_shared_across_pages(self):
		login_response = self.client.get(reverse('blog:home'))
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
		response = self.client.get(reverse('blog:post_detail', args=[course.pk]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, course.title)


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
