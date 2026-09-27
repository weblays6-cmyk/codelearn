from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import (
	Assignment,
	AssignmentAudience,
	AssignmentAttempt,
	AssignmentOption,
	AssignmentQuestion,
	Enrollment,
	Lesson,
	Post,
	PracticeProgress,
	PracticeSubmission,
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
