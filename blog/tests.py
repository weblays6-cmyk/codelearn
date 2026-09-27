from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.forms.models import inlineformset_factory

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
	Post,
	PracticeProgress,
	PracticeSubmission,
)
from .admin import AssignmentOptionInlineFormSet, AssignmentSubmissionAdmin

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
