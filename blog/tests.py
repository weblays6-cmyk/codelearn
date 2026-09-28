from datetime import timedelta
import json
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.forms.models import inlineformset_factory
from django.utils import timezone
from unittest.mock import MagicMock, patch

from .models import (
	Assignment,
	AssignmentAudience,
	AssignmentAttempt,
	AssignmentOption,
	AssignmentQuestion,
	AssignmentSubmission,
	Enrollment,
	Lesson,
	LessonProgress,
	Notification,
	Post,
	MockTest,
	MockTestAttempt,
	MockTestQuestion,
	PlaygroundSession,
	PracticeProblem,
	PracticeProblemSet,
	PracticeProgress,
	PracticeSubmission,
	Project,
)
from .admin import AssignmentOptionInlineFormSet, AssignmentSubmissionAdmin
from .services.code_execution import CodeRunnerUnavailable, run_code
from .services.leaderboard import leaderboard_rows

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

	def test_lesson_requires_enrollment(self):
		self.client.force_login(self.student)
		response = self.client.get(reverse('blog:lesson_detail', args=[self.lesson.pk]))
		self.assertRedirects(response, reverse('blog:post_detail', args=[self.course.pk]))

		Enrollment.objects.create(student=self.student, course=self.course)
		self.assertEqual(
			self.client.get(reverse('blog:lesson_detail', args=[self.lesson.pk])).status_code,
			200,
		)

	def test_lesson_completion_updates_enrollment_progress(self):
		Enrollment.objects.create(student=self.student, course=self.course)
		self.client.force_login(self.student)
		self.client.get(reverse('blog:lesson_detail', args=[self.lesson.pk]))

		lesson_progress = self.lesson.student_progress.get(student=self.student)
		self.assertFalse(lesson_progress.completed)

		response = self.client.post(reverse('blog:complete_lesson', args=[self.lesson.pk]))
		self.assertRedirects(response, reverse('blog:lesson_detail', args=[self.lesson.pk]))
		lesson_progress.refresh_from_db()
		enrollment = Enrollment.objects.get(student=self.student, course=self.course)
		self.assertTrue(lesson_progress.completed)
		self.assertEqual(enrollment.progress, 100)
		self.assertTrue(enrollment.completed)

		self.client.post(reverse('blog:complete_lesson', args=[self.lesson.pk]))
		self.assertEqual(LessonProgress.objects.filter(student=self.student, lesson=self.lesson).count(), 1)

	def test_lesson_start_is_persisted_and_sequential_access_is_enforced(self):
		second_lesson = Lesson.objects.create(
			course=self.course,
			title='Loops',
			content='Loop content',
			order=2,
		)
		self.course.sequential_learning = True
		self.course.save(update_fields=('sequential_learning',))
		Enrollment.objects.create(student=self.student, course=self.course)
		self.client.force_login(self.student)

		locked_response = self.client.get(reverse('blog:lesson_detail', args=[second_lesson.pk]))
		self.assertEqual(locked_response.status_code, 403)

		first_response = self.client.get(reverse('blog:lesson_detail', args=[self.lesson.pk]))
		self.assertEqual(first_response.status_code, 200)
		progress = LessonProgress.objects.get(student=self.student, lesson=self.lesson)
		enrollment = Enrollment.objects.get(student=self.student, course=self.course)
		self.assertIsNotNone(progress.started_at)
		self.assertIsNotNone(progress.last_accessed_at)
		self.assertIsNotNone(enrollment.started_at)
		self.assertIsNotNone(enrollment.last_accessed_at)

		self.client.post(reverse('blog:complete_lesson', args=[self.lesson.pk]))
		self.assertEqual(self.client.get(reverse('blog:lesson_detail', args=[second_lesson.pk])).status_code, 200)

	def test_start_lesson_route_enrolls_user_and_opens_lesson(self):
		self.client.force_login(self.student)
		self.assertFalse(Enrollment.objects.filter(student=self.student, course=self.course).exists())

		response = self.client.get(reverse('blog:start_lesson', args=[self.course.pk, self.lesson.pk]))
		self.assertEqual(response.status_code, 302)
		self.assertTrue(Enrollment.objects.filter(student=self.student, course=self.course).exists())
		self.assertEqual(response.url, reverse('blog:lesson_detail', args=[self.lesson.pk]))

	def test_assignment_rejects_mismatched_course_and_lesson(self):
		other_course = Post.objects.create(
			title='Django',
			content='Other course',
			author=self.admin,
		)
		assignment = Assignment(
			title='Invalid placement',
			description='Test',
			assignment_source='COURSE',
			course=other_course,
			lesson=self.lesson,
			created_by=self.admin,
		)
		with self.assertRaises(ValidationError):
			assignment.full_clean()

	def test_learning_state_is_isolated_between_users(self):
		assignment = Assignment.objects.create(
			title='Private Course Quiz',
			description='Test',
			assignment_source='COURSE',
			course=self.course,
			status='PUBLISHED',
			created_by=self.admin,
		)
		Enrollment.objects.create(student=self.student, course=self.course)
		self.client.force_login(self.student)
		self.client.post(reverse('blog:complete_lesson', args=[self.lesson.pk]))
		self.assertTrue(LessonProgress.objects.get(student=self.student, lesson=self.lesson).completed)
		self.assertEqual(self.client.get(reverse('blog:assignment_attempt', args=[assignment.pk])).status_code, 200)

		self.client.force_login(self.other_student)
		self.assertEqual(self.client.get(reverse('blog:assignment_attempt', args=[assignment.pk])).status_code, 403)
		self.assertFalse(LessonProgress.objects.filter(student=self.other_student, lesson=self.lesson).exists())

	def test_only_staff_can_manage_courses(self):
		self.client.force_login(self.student)
		response = self.client.get(reverse('blog:create_post'))
		self.assertEqual(response.status_code, 302)

		self.admin.is_staff = True
		self.admin.save(update_fields=('is_staff',))
		self.client.force_login(self.admin)
		self.assertEqual(self.client.get(reverse('blog:create_post')).status_code, 200)

	def test_single_choice_options_require_one_correct_answer(self):
		assignment = Assignment.objects.create(
			title='Python Quiz',
			description='Quiz',
			assignment_source='COURSE',
			course=self.course,
			assignment_type='QUIZ',
			created_by=self.admin,
		)
		question = AssignmentQuestion.objects.create(
			assignment=assignment,
			question='Which is Python?',
			question_type='SINGLE',
		)
		option_formset = inlineformset_factory(
			AssignmentQuestion,
			AssignmentOption,
			formset=AssignmentOptionInlineFormSet,
			fields=('option_text', 'is_correct', 'order'),
			extra=0,
		)
		formset = option_formset(
			data={
				'options-TOTAL_FORMS': '2',
				'options-INITIAL_FORMS': '0',
				'options-MIN_NUM_FORMS': '2',
				'options-MAX_NUM_FORMS': '1000',
				'options-0-option_text': 'Python',
				'options-0-is_correct': 'on',
				'options-0-order': '1',
				'options-1-option_text': 'Ruby',
				'options-1-order': '2',
			},
			instance=question,
			)
		self.assertTrue(formset.is_valid())

		invalid_formset = option_formset(
			data={
			'options-TOTAL_FORMS': '2',
			'options-INITIAL_FORMS': '0',
			'options-MIN_NUM_FORMS': '2',
			'options-MAX_NUM_FORMS': '1000',
			'options-0-option_text': 'Python',
			'options-0-is_correct': 'on',
			'options-0-order': '1',
			'options-1-option_text': 'Ruby',
			'options-1-is_correct': 'on',
			'options-1-order': '2',
			},
			instance=question,
		)
		self.assertFalse(invalid_formset.is_valid())

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
			required=True,
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
		self.client.post(reverse('blog:complete_lesson', args=[self.lesson.pk]))
		enrollment = Enrollment.objects.get(student=self.student, course=self.course)
		self.assertEqual(enrollment.progress, 50)
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
		enrollment.refresh_from_db()
		self.assertEqual(enrollment.progress, 100)
		self.assertTrue(enrollment.completed)

	def test_quiz_questions_follow_admin_order_and_count(self):
		Enrollment.objects.create(student=self.student, course=self.course)
		assignment = Assignment.objects.create(
			title='Admin Ordered Quiz',
			description='Test',
			assignment_type='QUIZ',
			course=self.course,
			status='PUBLISHED',
			created_by=self.admin,
		)
		question_2 = AssignmentQuestion.objects.create(
			assignment=assignment,
			question='Second question',
			question_type='SINGLE',
			order=2,
		)
		AssignmentOption.objects.create(question=question_2, option_text='Answer 2', is_correct=True)
		AssignmentOption.objects.create(question=question_2, option_text='Wrong 2')
		question_1 = AssignmentQuestion.objects.create(
			assignment=assignment,
			question='First question',
			question_type='SINGLE',
			order=1,
		)
		AssignmentOption.objects.create(question=question_1, option_text='Answer 1', is_correct=True)
		AssignmentOption.objects.create(question=question_1, option_text='Wrong 1')

		self.client.force_login(self.student)
		response = self.client.get(reverse('blog:assignment_attempt', args=[assignment.pk]))
		self.assertContains(response, 'Question 1')
		self.assertContains(response, 'Question 2')
		self.assertContains(response, 'First question')
		self.assertContains(response, 'Second question')
		self.assertLess(response.content.index(b'First question'), response.content.index(b'Second question'))

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
		self.assertTrue(submission.file.name.startswith('assignments/work'))
		self.assertTrue(submission.file.name.endswith('.txt'))

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


class CommunityAndNotificationTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user('community-user', password='pass')
		self.client.force_login(self.user)
		self.owner = User.objects.create_user('project-owner', password='pass')
		self.project = Project.objects.create(
			owner=self.owner,
			title='Build a Portfolio Site',
			short_description='A landing page with a contact form.',
			description='A full portfolio built with Django.',
			category='Web Development',
			status='live',
		)
		self.notification = Notification.objects.create(
			recipient=self.user,
			sender=self.owner,
			notification_type='FOLLOW_REQUEST',
			message='@project-owner sent you a follow request.',
		)

	def test_notifications_page_shows_user_notifications(self):
		response = self.client.get(reverse('blog:notifications'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Notifications')
		self.assertContains(response, 'follow request')
		self.assertTrue(response.context['notifications'].filter(id=self.notification.id).exists())

	def test_community_page_lists_real_projects(self):
		response = self.client.get(reverse('blog:community'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Developer Community')
		self.assertContains(response, self.project.title)
		self.assertContains(response, self.project.short_description)


class PracticeIntegrationTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user('practice-user', password='pass')
		self.client.force_login(self.user)

	def test_practice_page_uses_django_template(self):
		response = self.client.get(reverse('blog:practice'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Practice Arena')
		self.assertContains(response, 'practice.css')
		self.assertContains(response, reverse('blog:practice_playground'))
		self.assertContains(response, 'practice.js')
		self.assertContains(response, 'id="solverView"')

	def test_practice_pages_require_authentication(self):
		self.client.logout()
		response = self.client.get(reverse('blog:practice'))
		self.assertEqual(response.status_code, 302)

	def test_problem_workspace_renders_public_data_only(self):
		problem = PracticeProblem.objects.create(
			slug='private-case-problem', title='Private Case Problem', description='Public statement',
			difficulty='MEDIUM', function_name='solve', starter_code={'python': 'def solve(): pass'},
			example={'input': '1', 'output': '1'},
			public_tests=[{'input': '1', 'expected': '1'}],
			hidden_tests=[{'input': 'secret-case-input', 'expected': 'secret-case-output'}],
		)
		with patch('blog.views.runner_is_configured', return_value=False):
			response = self.client.get(reverse('blog:practice_problem_detail', args=[problem.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, problem.title)
		self.assertContains(response, 'Execution is disabled')
		self.assertNotContains(response, 'secret-case-input')
		self.assertNotContains(response, 'secret-case-output')

	def test_problem_library_server_filters(self):
		PracticeProblem.objects.create(
			slug='array-easy', title='Array Easy', description='Array search', difficulty='EASY',
			category='python', function_name='solve', starter_code={'python': 'def solve(): pass'},
		)
		PracticeProblem.objects.create(
			slug='array-hard', title='Array Hard', description='Array search', difficulty='HARD',
			category='python', function_name='solve', starter_code={'python': 'def solve(): pass'},
		)
		response = self.client.get(reverse('blog:practice_all'), {
			'search': 'Array', 'category': 'python', 'difficulty': 'EASY', 'status': 'NOT_ATTEMPTED',
		})
		self.assertContains(response, 'Array Easy')
		self.assertNotContains(response, 'Array Hard')

	def test_practice_subpages_are_live_and_data_driven(self):
		PracticeProblem.objects.create(
			slug='two-sum',
			title='Two Sum',
			description='Find two numbers.',
			difficulty='EASY',
			category='python',
			function_name='two_sum',
			starter_code={'python': 'def two_sum(nums, target):\n    pass'},
			public_tests=[{'input': [2, 7, 11, 15], 'target': 9}],
			hidden_tests=[],
		)
		practice_home = self.client.get(reverse('blog:practice'))
		self.assertContains(practice_home, 'practice-database-problems')
		self.assertContains(practice_home, '?problem=two-sum')

		for name in [
			'practice_details',
			'practice_all',
			'practice_playground',
			'practice_mock_tests',
			'practice_problem_sets',
			'practice_leaderboard',
		]:
			response = self.client.get(reverse(f'blog:{name}'))
			self.assertEqual(response.status_code, 200)

		self.assertContains(self.client.get(reverse('blog:practice_details')), 'Practice Overview')
		self.assertContains(self.client.get(reverse('blog:practice_all')), 'All Practice Problems')
		self.assertContains(self.client.get(reverse('blog:practice_playground')), 'Code Playground')
		self.assertContains(self.client.get(reverse('blog:practice_mock_tests')), 'Mock Tests')
		self.assertContains(self.client.get(reverse('blog:practice_problem_sets')), 'Problem Sets')
		self.assertContains(self.client.get(reverse('blog:practice_leaderboard')), 'Leaderboard')

	def test_practice_draft_and_runner_confirmed_submission_are_persisted(self):
		problem = PracticeProblem.objects.create(
			slug='two-sum',
			title='Two Sum',
			description='Find two numbers.',
			difficulty='EASY',
			function_name='two_sum',
			starter_code={'python': 'def two_sum(nums, target):\n    pass'},
			public_tests=[{'input': [2, 7], 'target': 9, 'expected': [0, 1]}],
			hidden_tests=[{'input': [3, 3], 'target': 6, 'expected': [0, 1]}],
		)
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
		progress = PracticeProgress.objects.get(user=self.user, problem=problem)
		self.assertIn('python', progress.code_drafts)

		with patch('blog.views.supported_languages', return_value=('python',)), patch('blog.views.run_code') as run_code:
			run_code.return_value = {
				'status': 'ACCEPTED',
				'stdout': '',
				'stderr': '',
				'execution_time_ms': 7,
				'memory_kb': 64,
				'test_results': [
					{'passed': True, 'input': 'nums=[2,7]', 'expected': '[0,1]', 'actual': '[0,1]', 'hidden': False},
					{'passed': True, 'input': 'secret input', 'expected': 'secret expected', 'actual': 'secret actual', 'hidden': True},
				],
			}
			submit_response = self.client.post(
				reverse('blog:practice_problem_submit', args=[problem.slug]),
			data={
				'language': 'python',
				'sourceCode': 'def two_sum(nums, target): return [0, 1]',
			},
			content_type='application/json',
			)
		self.assertEqual(submit_response.status_code, 200)
		self.assertNotContains(submit_response, 'secret input')
		progress.refresh_from_db()
		self.assertEqual(progress.status, 'SOLVED')
		submission = PracticeSubmission.objects.get(user=self.user, problem=problem)
		self.assertEqual(submission.passed_test_cases, 2)
		self.assertEqual(len(submission.result_data['visible_test_results']), 1)

	def test_previous_browser_solver_persists_problem_progress(self):
		response = self.client.post(
			reverse('blog:practice_record'),
			data={
				'kind': 'submit',
				'problemId': 'two-sum',
				'language': 'python',
				'sourceCode': 'def two_sum(nums, target): return [0, 1]',
				'status': 'ACCEPTED',
				'passed': 3,
				'total': 5,
			},
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 200)
		progress = PracticeProgress.objects.get(user=self.user, problem__slug='two-sum')
		self.assertEqual(progress.status, 'SOLVED')
		submission = PracticeSubmission.objects.get(user=self.user, problem=progress.problem)
		self.assertEqual(submission.passed_test_cases, 3)

	def test_playground_sessions_are_persisted_and_private(self):
		with patch('blog.views.supported_languages', return_value=('python',)):
			response = self.client.post(
				reverse('blog:playground_save'),
				data={'language': 'python', 'sourceCode': 'print(1)', 'stdin': '', 'title': 'Experiment'},
				content_type='application/json',
			)
		self.assertEqual(response.status_code, 200)
		session = PlaygroundSession.objects.get(user=self.user)
		self.assertEqual(session.source_code, 'print(1)')
		other = User.objects.create_user('other-practice-user', password='pass')
		self.client.force_login(other)
		response = self.client.get(reverse('blog:practice_playground'), {'session': session.pk})
		self.assertEqual(response.status_code, 404)

	def test_playground_fails_closed_when_runner_is_unavailable(self):
		with patch('blog.views.run_code', side_effect=CodeRunnerUnavailable('Code execution is not configured.')):
			response = self.client.post(
				reverse('blog:playground_run'),
				data={'language': 'python', 'sourceCode': 'print(1)', 'stdin': ''},
				content_type='application/json',
			)
		self.assertEqual(response.status_code, 503)
		self.assertIn('Code execution is not configured.', response.json()['error'])

	def test_problem_set_limits_problem_detail_to_members(self):
		member = PracticeProblem.objects.create(
			slug='array-problem', title='Array Problem', description='Member problem', difficulty='EASY',
			function_name='solve', starter_code={'python': 'def solve(): pass'},
		)
		nonmember = PracticeProblem.objects.create(
			slug='other-problem', title='Other Problem', description='Not in this set', difficulty='EASY',
			function_name='solve', starter_code={'python': 'def solve(): pass'},
		)
		problem_set = PracticeProblemSet.objects.create(title='Array Mastery', slug='array-mastery')
		problem_set.problems.add(member)
		response = self.client.get(reverse('blog:practice_problem_set_detail', args=[problem_set.slug]))
		self.assertContains(response, member.title)
		self.assertNotContains(response, nonmember.title)

	def test_mock_test_attempt_persists_answers_scores_and_ownership(self):
		mock_test = MockTest.objects.create(
			title='Python Basics', slug='python-basics', duration_minutes=20, active=True,
		)
		question = MockTestQuestion.objects.create(
			test=mock_test, prompt='Which keyword defines a function?',
			options=[{'id': 'a', 'text': 'function'}, {'id': 'b', 'text': 'def'}],
			correct_answer='b', explanation='Python uses def.', points=5,
		)
		detail_response = self.client.get(reverse('blog:practice_mock_test_detail', args=[mock_test.pk]))
		self.assertContains(detail_response, mock_test.title)
		self.assertContains(detail_response, 'Start Test')
		self.assertNotContains(detail_response, 'Python uses def.')
		start = self.client.post(reverse('blog:practice_mock_test_start', args=[mock_test.pk]))
		self.assertEqual(start.status_code, 302)
		attempt = MockTestAttempt.objects.get(user=self.user, test=mock_test)
		deadline = attempt.expires_at
		attempt_page = self.client.get(reverse('blog:practice_mock_test_attempt', args=[attempt.pk]))
		self.assertNotContains(attempt_page, 'Python uses def.')
		attempt.refresh_from_db()
		self.assertEqual(attempt.expires_at, deadline)
		answer_response = self.client.post(
			reverse('blog:practice_mock_test_answer', args=[attempt.pk]),
			data={'questionId': question.pk, 'answer': 'b'},
			content_type='application/json',
		)
		self.assertEqual(answer_response.status_code, 200)
		submit = self.client.post(reverse('blog:practice_mock_test_submit', args=[attempt.pk]))
		self.assertEqual(submit.status_code, 302)
		attempt.refresh_from_db()
		self.assertEqual(attempt.status, 'COMPLETED')
		self.assertEqual(attempt.score, 5)
		self.assertEqual(attempt.total_score, 5)
		self.assertEqual(self.client.post(reverse('blog:practice_mock_test_submit', args=[attempt.pk])).status_code, 409)
		self.assertContains(self.client.get(reverse('blog:practice_mock_test_result', args=[attempt.pk]) + '?review=1'), 'Correct answer')
		other = User.objects.create_user('mock-test-other', password='pass')
		self.client.force_login(other)
		self.assertEqual(self.client.get(reverse('blog:practice_mock_test_attempt', args=[attempt.pk])).status_code, 404)

	def test_mock_test_expiry_is_finalized_on_server(self):
		mock_test = MockTest.objects.create(title='Expiry', slug='expiry', duration_minutes=1, active=True)
		MockTestQuestion.objects.create(test=mock_test, prompt='Q', options=[{'id': 'x', 'text': 'X'}], correct_answer='x')
		self.client.post(reverse('blog:practice_mock_test_start', args=[mock_test.pk]))
		attempt = MockTestAttempt.objects.get(user=self.user, test=mock_test)
		MockTestAttempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
		response = self.client.get(reverse('blog:practice_mock_test_attempt', args=[attempt.pk]))
		self.assertEqual(response.status_code, 302)
		attempt.refresh_from_db()
		self.assertEqual(attempt.status, 'EXPIRED')

	def test_leaderboard_scoring_is_deterministic_and_retakes_do_not_stack(self):
		problem = PracticeProblem.objects.create(
			slug='medium-problem', title='Medium Problem', description='Test', difficulty='MEDIUM',
			function_name='solve', starter_code={'python': 'def solve(): pass'},
		)
		PracticeProgress.objects.create(
			user=self.user, problem=problem, status='SOLVED', solved_at=timezone.now(), attempt_count=2,
		)
		PracticeSubmission.objects.create(
			user=self.user, problem=problem, language='python', source_code='solve()', status='ACCEPTED',
			passed_test_cases=2, total_test_cases=2,
		)
		PracticeSubmission.objects.create(
			user=self.user, problem=problem, language='python', source_code='solve()', status='ACCEPTED',
			passed_test_cases=2, total_test_cases=2,
		)
		mock_test = MockTest.objects.create(title='Scored Test', slug='scored-test')
		for score in (6, 9):
			MockTestAttempt.objects.create(
				user=self.user, test=mock_test, expires_at=timezone.now(), submitted_at=timezone.now(),
				score=score, total_score=10, status='COMPLETED',
			)

		rows, period = leaderboard_rows('all')
		self.assertEqual(period, 'all')
		self.assertEqual(rows[0]['user'], self.user)
		self.assertEqual(rows[0]['solved'], 1)
		self.assertEqual(rows[0]['tests'], 1)
		self.assertEqual(rows[0]['points'], 29)

	def test_external_runner_redacts_hidden_test_diagnostics(self):
		response = MagicMock()
		response.read.return_value = json.dumps({
			'status': 'ACCEPTED',
			'test_results': [
				{'passed': False, 'input': 'private input', 'expected': 'secret', 'actual': 'answer', 'hidden': True},
			],
		}).encode()
		opener = MagicMock()
		opener.open.return_value.__enter__.return_value = response
		with patch.dict('os.environ', {
			'CODE_RUNNER_URL': 'https://runner.example.test/execute',
			'CODE_RUNNER_LANGUAGES': 'python',
		}), patch('blog.services.code_execution.urllib.request.build_opener', return_value=opener):
			result = run_code(
				source_code='def solution(): pass',
				language='python',
				test_cases=[{'input': 'server-only'}],
				submit=True,
			)
		self.assertTrue(result['test_results'][0]['hidden'])
		self.assertEqual(result['test_results'][0]['input'], '')
		self.assertEqual(result['test_results'][0]['expected'], '')
