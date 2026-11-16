from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.test import override_settings

from blog.models import (
    Comment,
    CourseCertificate,
    CourseReview,
    CourseWishlist,
    Enrollment,
    Lesson,
    LessonProgress,
    LessonNote,
    Module,
    ModuleQuiz,
    Post,
    Payment,
    SubscriptionPlan,
    QuizAttempt,
    QuizQuestion,
)
from blog.services.course_progress import can_access_lesson, mark_lesson_completed
from blog.services.payments import RazorpayProvider, complete_payment


class CourseLearningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.user = user_model.objects.create_user(username='course-learner', password='test-password')
        cls.other = user_model.objects.create_user(username='other-learner', password='test-password')
        cls.course = Post.objects.create(
            title='Course test',
            slug='course-test',
            category='Python',
            difficulty='Beginner',
            description='Test course description',
            content='Course overview',
            author=cls.user,
            status='PUBLISHED',
        )
        cls.module = Module.objects.create(course=cls.course, title='Foundations', order=1)
        cls.lesson_one = Lesson.objects.create(
            course=cls.course,
            module=cls.module,
            title='Lesson one',
            slug='course-lesson-one',
            content='# Lesson\n\n```python\nprint("safe")\n```',
            order=1,
        )
        cls.lesson_two = Lesson.objects.create(
            course=cls.course,
            module=cls.module,
            title='Lesson two',
            slug='course-lesson-two',
            content='Next lesson.',
            order=2,
        )
        cls.quiz = ModuleQuiz.objects.create(module=cls.module, title='Foundations quiz', passing_score=70)
        for order in range(1, 6):
            QuizQuestion.objects.create(
                quiz=cls.quiz,
                prompt=f'Question {order}',
                options=['Incorrect', 'Correct', 'Also incorrect'],
                correct_option=1,
                explanation='Choose the correct option.',
                order=order,
            )
        cls.enrollment = Enrollment.objects.create(student=cls.user, course=cls.course)

    def setUp(self):
        self.client.force_login(self.user)

    def test_catalog_detail_lesson_quiz_and_certificate_smoke(self):
        response = self.client.get(reverse('blog:blogpage'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('{{', response.content.decode())
        response = self.client.get(reverse('blog:post_detail', args=(self.course.slug,)))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('{{', response.content.decode())
        self.assertContains(response, 'course-action-row')
        self.assertContains(response, 'Save to wishlist')
        self.assertContains(response, 'Share course')
        response = self.client.get(reverse('blog:lesson_detail', args=(self.lesson_one.slug,)))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('{{', response.content.decode())
        response = self.client.get(reverse('blog:module_quiz', args=(self.quiz.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('{{', response.content.decode())
        certificate = CourseCertificate.objects.create(enrollment=self.enrollment)
        response = self.client.get(reverse('blog:course_certificate', args=(certificate.verification_code,)))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('blog:verify_certificate', args=(certificate.verification_code,)))
        self.assertEqual(response.status_code, 404)
        self.enrollment.progress = 100
        self.enrollment.completed = True
        self.enrollment.save(update_fields=('progress', 'completed'))
        response = self.client.get(reverse('blog:verify_certificate', args=(certificate.verification_code,)))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('{{', response.content.decode())

    def test_enroll_without_duplicates_and_unenroll(self):
        self.enrollment.delete()
        url = reverse('blog:post_detail', args=(self.course.slug,))
        for _ in range(2):
            response = self.client.post(url, {'action': 'enroll'})
            self.assertEqual(response.status_code, 302)
        self.assertEqual(Enrollment.objects.filter(student=self.user, course=self.course).count(), 1)
        response = self.client.post(url, {'action': 'unenroll'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Enrollment.objects.filter(student=self.user, course=self.course).exists())

    def test_learn_free_enrolls_once_and_rejects_paid_courses(self):
        Enrollment.objects.filter(student=self.user, course=self.course).delete()
        url = reverse('blog:post_detail', args=(self.course.slug,))
        first_response = self.client.post(url, {'action': 'enroll_free'})
        self.assertRedirects(first_response, reverse('blog:lesson_detail', args=(self.lesson_one.slug,)), fetch_redirect_response=False)
        self.assertContains(self.client.get(first_response.url), 'You are enrolled')
        second_response = self.client.post(url, {'action': 'enroll_free'})
        self.assertRedirects(second_response, reverse('blog:lesson_detail', args=(self.lesson_one.slug,)), fetch_redirect_response=False)
        self.assertEqual(Enrollment.objects.filter(student=self.user, course=self.course).count(), 1)
        self.assertIsNone(Enrollment.objects.get(student=self.user, course=self.course).certificate_code)

        Enrollment.objects.filter(student=self.user, course=self.course).delete()
        self.course.access = 'paid'
        self.course.is_free = False
        self.course.price = '199.00'
        self.course.save(update_fields=('access', 'is_free', 'price'))
        self.client.post(url, {'action': 'enroll_free'})
        self.assertTrue(Enrollment.objects.filter(student=self.user, course=self.course).exists())

        plan = SubscriptionPlan.objects.create(name='Course premium', slug='course-premium', price='199.00')
        profile = self.user.profile_data
        profile.plan = 'premium'
        profile.subscription_plan = plan
        profile.plan_expires_at = timezone.now() + timedelta(days=30)
        profile.save(update_fields=('plan', 'subscription_plan', 'plan_expires_at'))
        self.client.post(url, {'action': 'enroll_free'})
        self.assertEqual(Enrollment.objects.filter(student=self.user, course=self.course).count(), 1)

    def test_enrollment_certificate_code_is_issued_only_at_completion(self):
        enrollment = self.enrollment
        self.assertIsNone(enrollment.certificate_code)

        halfway = mark_lesson_completed(self.user, self.lesson_one)
        self.assertEqual(halfway.progress, 50)
        self.assertIsNone(halfway.certificate_code)
        self.assertFalse(CourseCertificate.objects.filter(enrollment=enrollment).exists())

        completed = mark_lesson_completed(self.user, self.lesson_two)
        self.assertEqual(completed.progress, 100)
        self.assertTrue(completed.certificate_code)
        self.assertEqual(CourseCertificate.objects.filter(enrollment=enrollment).count(), 1)

    def test_advanced_lesson_page_shows_upgrade_without_content(self):
        self.lesson_two.level = 'advanced'
        self.lesson_two.content = 'PRIVATE_ADVANCED_LESSON_BODY'
        self.lesson_two.save(update_fields=('level', 'content'))

        response = self.client.get(reverse('blog:lesson_detail', args=(self.lesson_two.slug,)))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Unlock this lesson')
        self.assertContains(response, 'Advanced · Premium')
        self.assertContains(response, 'Payments coming soon.')
        self.assertNotContains(response, 'PRIVATE_ADVANCED_LESSON_BODY')

    def test_wishlist_ajax_toggle_and_empty_state(self):
        url = reverse('blog:course_save', args=(self.course.slug,))
        response = self.client.post(
            url,
            {'action': 'toggle'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'saved': True, 'count': 1})
        self.assertEqual(CourseWishlist.objects.filter(user=self.user, course=self.course).count(), 1)
        response = self.client.post(
            url,
            {'action': 'toggle'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertJSONEqual(response.content, {'saved': False, 'count': 0})
        self.assertEqual(self.client.get(reverse('blog:course_wishlist')).status_code, 200)
        self.assertContains(self.client.get(reverse('blog:course_wishlist')), 'Add your courses')

    def test_student_discussion_post_returns_avatar_and_saved_comment(self):
        response = self.client.post(
            reverse('blog:course_detail', args=(self.course.slug,)),
            {'action': 'comment', 'content': 'This explanation helped.'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['comment']['username'], self.user.username)
        self.assertEqual(Comment.objects.filter(post=self.course, author=self.user).count(), 1)

    def test_my_learning_paginates_six_courses_and_formats_study_time(self):
        LessonProgress.objects.create(
            student=self.user,
            lesson=self.lesson_one,
            completed=True,
            completed_at=timezone.now(),
        )
        for index in range(6):
            course = Post.objects.create(
                title=f'Learning course {index}',
                slug=f'learning-course-{index}',
                description='Learning course.',
                content='Overview.',
                author=self.user,
            )
            Enrollment.objects.create(student=self.user, course=course)

        response = self.client.get(reverse('blog:my_learning'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['enrollments'].paginator.per_page, 6)
        self.assertEqual(response.context['enrollments'].paginator.count, 7)
        self.assertEqual(response.context['estimated_study_minutes'], max(1, (len(self.lesson_one.content) + 1199) // 1200))
        self.assertContains(response, '0h 1m')

    def test_catalog_filters_and_compact_pagination(self):
        response = self.client.get(reverse('blog:blogpage'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Find Your')
        self.assertContains(response, 'All topics')
        self.assertEqual(response.context['posts'].paginator.num_pages, 1)
        self.assertEqual(response.context['posts'].paginator.per_page, 9)
        self.assertContains(response, 'mobile-filter-trigger')
        self.assertContains(response, 'course-filter-fields')
        default_content = response.content.decode()
        self.assertIn('Showing 1-1 of 1 courses', default_content)
        self.assertEqual(default_content.count('Showing '), 1)
        self.assertEqual(default_content.count('class="filter-chip"'), 0)
        self.assertNotIn('Clear all', default_content)

        for index in range(10):
            Post.objects.create(
                title=f'Pagination course {index}',
                slug=f'pagination-course-{index}',
                description='Course for pagination.',
                content='Course content.',
                author=self.user,
            )
        response = self.client.get(reverse('blog:blogpage'), {
            'search': 'Pagination',
            'category': 'Python',
            'price': 'free',
        })
        self.assertEqual(response.context['posts'].paginator.num_pages, 2)
        self.assertContains(response, 'Next')
        self.assertContains(response, 'name="sort"')
        self.assertContains(response, 'search=Pagination&amp;category=Python&amp;price=free&amp;page=2')
        filtered_content = response.content.decode()
        self.assertIn('Topic: Python', filtered_content)
        self.assertIn('Price: Free', filtered_content)
        self.assertNotIn('Level:', filtered_content)
        self.assertIn('Showing 1-9 of 10 courses', filtered_content)
        self.assertEqual(filtered_content.count('Showing '), 1)

    def test_learning_path_continue_targets_first_unfinished_course(self):
        first_course = Post.objects.create(
            title='Python Fundamentals',
            slug='python-fundamentals',
            category='Python',
            difficulty='Beginner',
            description='Start with Python.',
            content='Course overview.',
            author=self.user,
            status='PUBLISHED',
        )
        next_course = Post.objects.create(
            title='Django for Beginners',
            slug='django-for-beginners',
            category='Django',
            difficulty='Beginner',
            description='Continue with Django.',
            content='Course overview.',
            author=self.user,
            status='PUBLISHED',
        )
        Enrollment.objects.create(student=self.user, course=first_course, completed=True)

        response = self.client.get(reverse('blog:blogpage'))

        path = next(
            item for item in response.context['learning_paths']
            if item['title'] == 'Python > Django > Full Stack'
        )
        expected_url = reverse('blog:course_detail', kwargs={'slug': next_course.slug})
        self.assertEqual(path['continue_url'], expected_url)
        self.assertContains(response, f'href="{expected_url}" class="path-continue-button"')

    def test_advanced_lessons_require_an_unexpired_premium_plan(self):
        self.lesson_two.level = 'intermediate'
        self.lesson_two.save(update_fields=('level',))
        self.assertTrue(can_access_lesson(self.user, self.lesson_one))
        self.assertTrue(can_access_lesson(self.user, self.lesson_two))

        self.lesson_two.level = 'advanced'
        self.lesson_two.save(update_fields=('level',))
        self.assertFalse(can_access_lesson(self.user, self.lesson_two))

        self.course.access = 'paid'
        self.course.save(update_fields=('access',))
        self.lesson_two.level = 'intermediate'
        self.lesson_two.save(update_fields=('level',))
        self.assertTrue(can_access_lesson(self.user, self.lesson_two))
        self.lesson_two.level = 'advanced'
        self.lesson_two.save(update_fields=('level',))
        self.assertFalse(can_access_lesson(self.user, self.lesson_two))

        profile = self.user.profile_data
        profile.plan = 'premium'
        profile.plan_expires_at = timezone.now() + timedelta(days=1)
        profile.save(update_fields=('plan', 'plan_expires_at'))
        self.assertTrue(can_access_lesson(self.user, self.lesson_two))

        profile.plan_expires_at = timezone.now() - timedelta(seconds=1)
        profile.save(update_fields=('plan_expires_at',))
        self.assertFalse(can_access_lesson(self.user, self.lesson_two))

    def test_progress_calculation_issues_certificate_at_completion(self):
        self.assertEqual(mark_lesson_completed(self.user, self.lesson_one).progress, 50)
        enrollment = mark_lesson_completed(self.user, self.lesson_two)
        self.assertEqual(enrollment.progress, 100)
        self.assertTrue(enrollment.completed)
        certificate = CourseCertificate.objects.get(enrollment=enrollment)
        self.assertEqual(CourseCertificate.objects.filter(enrollment=enrollment).count(), 1)
        self.assertEqual(
            self.client.get(reverse('blog:verify_certificate', args=(certificate.verification_code,))).status_code,
            200,
        )

    def test_one_review_per_enrolled_user(self):
        url = reverse('blog:post_detail', args=(self.course.slug,))
        for rating, text in ((4, 'Useful'), (5, 'Excellent')):
            response = self.client.post(url, {'action': 'review', 'rating': rating, 'review': text})
            self.assertEqual(response.status_code, 302)
        self.assertEqual(CourseReview.objects.filter(user=self.user, course=self.course).count(), 1)
        self.assertEqual(CourseReview.objects.get(user=self.user, course=self.course).rating, 5)

    def test_quiz_scoring_pass_mark_and_first_pass_xp(self):
        data = {f'question_{question.pk}': (1 if question.order <= 4 else 0) for question in self.quiz.questions.all()}
        response = self.client.post(reverse('blog:module_quiz', args=(self.quiz.pk,)), data)
        self.assertEqual(response.status_code, 200)
        attempt = QuizAttempt.objects.latest('pk')
        self.assertEqual(attempt.score, 80)
        self.assertTrue(attempt.passed)
        self.assertTrue(response.context['attempt'].passed)
        failed_data = {f'question_{question.pk}': (1 if question.order <= 3 else 0) for question in self.quiz.questions.all()}
        self.client.post(reverse('blog:module_quiz', args=(self.quiz.pk,)), failed_data)
        self.assertFalse(QuizAttempt.objects.latest('pk').passed)
        self.assertEqual(QuizAttempt.objects.filter(user=self.user, quiz=self.quiz).count(), 2)

    def test_notes_are_private_and_bookmarks_are_idempotent(self):
        url = reverse('blog:lesson_notes', args=(self.lesson_one.slug,))
        response = self.client.post(url, {'action': 'save', 'content': 'My note'})
        self.assertEqual(response.status_code, 302)
        note = LessonNote.objects.get(user=self.user, lesson=self.lesson_one)
        other_client = self.client_class()
        other_client.force_login(self.other)
        self.assertEqual(other_client.post(url, {'action': 'delete'}).status_code, 403)
        self.assertTrue(LessonNote.objects.filter(pk=note.pk, user=self.user).exists())
        bookmark_url = reverse('blog:lesson_bookmark', args=(self.lesson_one.slug,))
        other_client = self.client
        for _ in range(2):
            self.assertEqual(other_client.post(bookmark_url).status_code, 302)
        self.assertFalse(self.user.lesson_bookmarks.filter(lesson=self.lesson_one).exists())

    def test_course_seed_is_idempotent(self):
        staff = get_user_model().objects.create_user(
            username='course-seed-instructor',
            password='test-password',
            is_staff=True,
        )
        call_command('seed_courses', username=staff.username, verbosity=0)
        call_command('seed_courses', username=staff.username, verbosity=0)
        seeded = Post.objects.filter(slug__in=(
            'python-fundamentals',
            'django-for-beginners',
            'sql-essentials',
            'javascript-basics',
            'html-css',
            'data-structures',
        ))
        self.assertEqual(seeded.count(), 6)
        self.assertEqual(Module.objects.filter(course__in=seeded).count(), 12)
        self.assertEqual(Lesson.objects.filter(course__in=seeded).count(), 48)
        self.assertEqual(ModuleQuiz.objects.filter(module__course__in=seeded).count(), 12)
        self.assertEqual(QuizQuestion.objects.filter(quiz__module__course__in=seeded).count(), 60)
        self.assertEqual(CourseWishlist.objects.filter(user=self.user).count(), 0)


class PaymentServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='payment-learner', password='test-password')
        self.plan = SubscriptionPlan.objects.create(
            name='Premium monthly',
            slug='premium-monthly',
            price='199.00',
            duration_days=30,
            features=['Advanced lessons'],
        )

    @override_settings(RAZORPAY_KEY_ID='test-key', RAZORPAY_KEY_SECRET='test-secret')
    def test_signature_verification_rejects_invalid_signatures(self):
        provider = RazorpayProvider()
        import hashlib
        import hmac
        signature = hmac.new(
            b'test-secret',
            b'order_123|pay_123',
            hashlib.sha256,
        ).hexdigest()

        self.assertTrue(provider.verify_payment_signature('order_123', 'pay_123', signature))
        self.assertFalse(provider.verify_payment_signature('order_123', 'pay_123', 'invalid'))

    def test_payment_completion_is_idempotent_and_activates_plan_once(self):
        payment = Payment.objects.create(
            user=self.user,
            plan=self.plan,
            amount=self.plan.price,
            provider_order_id='order_123',
        )

        completed, changed = complete_payment(payment, 'pay_123')
        repeated, changed_again = complete_payment(payment, 'pay_123')

        self.assertTrue(changed)
        self.assertFalse(changed_again)
        self.assertEqual(completed.pk, repeated.pk)
        self.assertEqual(Payment.objects.filter(status='paid').count(), 1)
        self.user.profile_data.refresh_from_db()
        self.assertEqual(self.user.profile_data.plan, 'premium')
        self.assertEqual(self.user.profile_data.subscription_plan, self.plan)
        self.assertGreater(self.user.profile_data.plan_expires_at, timezone.now())
        self.assertEqual(self.user.notifications.filter(notification_type='PAYMENT_SUCCESS').count(), 1)

    @override_settings(RAZORPAY_KEY_ID='', RAZORPAY_KEY_SECRET='')
    def test_checkout_without_keys_returns_payments_coming_soon(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('blog:payment_create_order', args=(self.plan.slug,)))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['available'], False)
        self.assertEqual(response.json()['message'], 'Payments coming soon.')
        self.assertFalse(Payment.objects.exists())
