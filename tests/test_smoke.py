from html.parser import HTMLParser
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import uuid

from blog.models import (
    Assignment,
    AssignmentAttempt,
    AssignmentAudience,
    AITutorConversation,
    Conversation,
    CourseCertificate,
    Enrollment,
    FollowRequest,
    Lesson,
    Module,
    ModuleQuiz,
    Post,
    PracticeProblem,
    PracticeProgress,
    PracticeProblemSet,
    PlaygroundSession,
    MockTest,
    MockTestAttempt,
    MockTestQuestion,
    SiteSettings,
    UserAssignmentProgress,
)


class ScopedPageSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="smoke-user",
            password="SmokeTest!2026",
            first_name="Smoke",
        )
        cls.user.profile_data.onboarding_completed = True
        cls.user.profile_data.save(update_fields=("onboarding_completed",))
        cls.peer = get_user_model().objects.create_user(
            username="smoke-peer",
            password="smoke-test-password",
            first_name="Peer",
        )
        FollowRequest.objects.create(
            sender=cls.peer,
            receiver=cls.user,
            status="ACCEPTED",
        )
        FollowRequest.objects.create(
            sender=cls.user,
            receiver=cls.peer,
            status="ACCEPTED",
        )
        cls.conversation = Conversation.objects.create(
            project_owner=cls.peer,
            participant=cls.user,
            status="REQUEST",
            request_sender=cls.peer,
        )
        cls.problem = PracticeProblem.objects.create(
            slug="smoke-practice-problem",
            title="Smoke practice problem",
            description="A smoke-test problem.",
            difficulty="EASY",
            function_name="solve",
            starter_code={},
            public_tests=[],
            hidden_tests=[],
        )
        cls.problem_set = PracticeProblemSet.objects.create(
            title="Smoke Problem Set",
            slug="smoke-problem-set",
            active=True,
        )
        cls.problem_set.problems.add(cls.problem)
        cls.mock_test = MockTest.objects.create(
            title="Smoke Mock Test",
            slug="smoke-mock-test",
            description="Mock test smoke test.",
            duration_minutes=10,
            active=True,
        )
        cls.mock_question = MockTestQuestion.objects.create(
            test=cls.mock_test,
            prompt="Smoke question?",
            options=[{"id": "a", "text": "Answer"}],
            correct_answer="a",
            order=1,
        )
        cls.mock_attempt = MockTestAttempt.objects.create(
            user=cls.user,
            test=cls.mock_test,
            expires_at=timezone.now() + timedelta(minutes=10),
            total_score=1,
        )
        cls.completed_mock_attempt = MockTestAttempt.objects.create(
            user=cls.user,
            test=cls.mock_test,
            expires_at=timezone.now() - timedelta(minutes=1),
            submitted_at=timezone.now(),
            answers={str(cls.mock_question.pk): "a"},
            score=1,
            total_score=1,
            status="COMPLETED",
        )
        cls.shared_session = PlaygroundSession.objects.create(
            user=cls.user,
            title="Smoke shared session",
            language="python",
            source_code="print('hello')",
            share_token=uuid.uuid4(),
        )
        cls.course = Post.objects.create(
            title="Smoke Course",
            slug="smoke-course",
            category="Python",
            difficulty="Beginner",
            description="Course page smoke test.",
            content="Course overview.",
            author=cls.peer,
            status="PUBLISHED",
        )
        cls.module = Module.objects.create(course=cls.course, title="Smoke Module", order=1)
        cls.lesson = Lesson.objects.create(
            course=cls.course,
            module=cls.module,
            title="Smoke Lesson",
            slug="smoke-lesson",
            content="# Smoke lesson\n\n```python\nprint('ok')\n```",
            order=1,
        )
        cls.quiz = ModuleQuiz.objects.create(module=cls.module, title="Smoke Quiz")
        cls.enrollment = Enrollment.objects.create(
            student=cls.user,
            course=cls.course,
            completed=True,
            progress=100,
        )
        cls.certificate = CourseCertificate.objects.create(enrollment=cls.enrollment)
        cls.assignment = Assignment.objects.create(
            title="Smoke Assignment",
            description="Smoke assignment instructions.",
            instructions="# Instructions\n\nSubmit a short response.",
            assignment_source="STANDALONE",
            assignment_type="TEXT",
            status="PUBLISHED",
            created_by=cls.peer,
        )
        AssignmentAudience.objects.create(
            assignment=cls.assignment,
            audience_type="ALL_USERS",
        )
        cls.staff = get_user_model().objects.create_user(
            username="smoke-staff",
            password="smoke-password",
            is_staff=True,
        )
        cls.ai_conversation = AITutorConversation.objects.create(
            user=cls.user,
            title="Smoke AI chat",
            last_active_at=timezone.now(),
            share_token=uuid.uuid4(),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def assert_clean_html(self, html):
        self.assertNotIn("{{", html)
        self.assertNotIn("{%", html)

    def test_practice_filter_controls_render_without_inline_clipping(self):
        class FilterFormParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_filter_form = False
                self.controls = []

            def handle_starttag(self, tag, attrs):
                attributes = dict(attrs)
                classes = attributes.get("class", "").split()
                if tag == "form" and "practice-filters" in classes:
                    self.in_filter_form = True
                    self.controls.append((tag, attributes))
                elif self.in_filter_form and tag in {"input", "select", "a", "button"}:
                    self.controls.append((tag, attributes))

            def handle_endtag(self, tag):
                if tag == "form" and self.in_filter_form:
                    self.in_filter_form = False

        response = self.client.get(reverse("blog:practice"))
        self.assertEqual(response.status_code, 200)

        parser = FilterFormParser()
        parser.feed(response.content.decode())
        control_ids = {
            attributes.get("id")
            for tag, attributes in parser.controls
            if tag in {"input", "select"}
        }

        self.assertTrue(parser.controls)
        self.assertTrue({
            "problemSearch",
            "difficultyFilter",
            "topicFilter",
            "statusFilter",
            "sortFilter",
        }.issubset(control_ids))
        self.assertFalse(any(attributes.get("style") for _, attributes in parser.controls))
        self.assertFalse(any(
            tag == "button" and "filters-apply" in attributes.get("class", "").split()
            for tag, attributes in parser.controls
        ))
        self.assertContains(response, 'id="filtersClear"')

    def test_profile_and_settings_controls_render_in_their_scoped_layouts(self):
        profile_response = self.client.get(reverse("blog:profile"))
        self.assertEqual(profile_response.status_code, 200)
        self.assertContains(profile_response, 'id="profile-edit"')
        self.assertContains(profile_response, 'id="shareProfileButton"')
        self.assertContains(profile_response, reverse("blog:followers_list", args=(self.user.username,)))
        self.assertContains(profile_response, "Github URL")
        self.assertContains(profile_response, "LinkedIn URL")

        settings_response = self.client.get(reverse("blog:settings"))
        self.assertEqual(settings_response.status_code, 200)
        for section in (
            "settings-account",
            "settings-privacy",
            "settings-notifications",
            "settings-appearance",
            "settings-security",
            "settings-app",
            "settings-danger",
        ):
            self.assertContains(settings_response, f'id="{section}"')
        for state in ("ready", "installed", "unsupported"):
            self.assertContains(settings_response, f'data-install-state="{state}"')
        self.assertContains(settings_response, 'name="notify_follows"')
        self.assertContains(settings_response, 'class="login-history-heading"')
        self.assertNotContains(settings_response, "IP:")
        self.assertEqual(
            settings_response.content.decode().count('id="installAppButton"'),
            1,
        )

    def test_scoped_pages_render_without_template_artifacts(self):
        page_names = (
            "dashboard",
            "blogpage",
            "my_learning",
            "practice",
            "practice_details",
            "practice_all",
            "practice_playground",
            "practice_mock_tests",
            "practice_leaderboard",
            "assignments",
            "ai_tutor",
            "projects",
            "community",
            "messages",
            "notifications",
            "follow_requests",
            "profile",
            "settings",
        )

        for page_name in page_names:
            with self.subTest(page=page_name):
                response = self.client.get(reverse(f"blog:{page_name}"))
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assert_clean_html(html)
                self.assertNotIn("Not_Attempted", html)
                self.assertNotIn("django_dev", html)

        for url in (
            reverse("blog:assignment_attempt", args=(self.assignment.pk,)),
            reverse("blog:assignment_scores"),
            reverse("blog:assignments") + "?view=calendar",
            reverse("blog:ai_tutor_share", args=(self.ai_conversation.share_token,)),
        ):
            with self.subTest(assignment_scope_url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assert_clean_html(html)
                self.assertNotIn("Not_Attempted", html)

        staff_client = self.client_class()
        staff_client.force_login(self.staff)
        evaluation = staff_client.get(reverse("blog:assignment_evaluate", args=(self.assignment.pk,)))
        self.assertEqual(evaluation.status_code, 200)
        self.assert_clean_html(evaluation.content.decode())

        for url in (
            reverse("blog:post_detail", args=(self.course.slug,)),
            reverse("blog:lesson_detail", args=(self.lesson.slug,)),
            reverse("blog:module_quiz", args=(self.quiz.pk,)),
            reverse("blog:course_certificate", args=(self.certificate.verification_code,)),
            reverse("blog:verify_certificate", args=(self.certificate.verification_code,)),
        ):
            with self.subTest(course_scope_url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assert_clean_html(html)
                self.assertNotIn("Not_Attempted", html)

        response = self.client.get(
            reverse(
                "blog:practice_problem_detail",
                kwargs={"slug": self.problem.slug},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assert_clean_html(response.content.decode())
        self.assertNotIn("Not_Attempted", response.content.decode())

        scoped_practice_urls = (
            reverse("blog:practice_problem_set_detail", args=(self.problem_set.slug,)),
            reverse("blog:practice_mock_test_detail", args=(self.mock_test.pk,)),
            reverse("blog:practice_mock_test_attempt", args=(self.mock_attempt.pk,)),
            reverse("blog:practice_mock_test_result", args=(self.completed_mock_attempt.pk,)),
            reverse("blog:playground_share", args=(self.shared_session.share_token,)),
        )
        for url in scoped_practice_urls:
            with self.subTest(practice_scope_url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assert_clean_html(html)
                self.assertNotIn("Not_Attempted", html)

        response = self.client.get(
            reverse("blog:conversation_detail", args=(self.conversation.pk,))
        )
        self.assertEqual(response.status_code, 200)
        self.assert_clean_html(response.content.decode())

        for page_name in ("followers_list", "following_list"):
            response = self.client.get(
                reverse(
                    f"blog:{page_name}",
                    kwargs={"username": self.user.username},
                )
            )
            self.assertEqual(response.status_code, 200)
            self.assert_clean_html(response.content.decode())

    def test_navigation_and_live_endpoints_resolve_for_a_normal_user(self):
        navigation_response = self.client.get(reverse("blog:dashboard"))
        self.assertEqual(navigation_response.status_code, 200)
        for page_name in (
            "dashboard",
            "blogpage",
            "my_learning",
            "practice",
            "assignments",
            "ai_tutor",
            "projects",
            "community",
            "messages",
            "notifications",
            "follow_requests",
            "profile",
            "settings",
        ):
            with self.subTest(navigation_target=page_name):
                self.assertContains(
                    navigation_response,
                    f'href="{reverse(f"blog:{page_name}")}"',
                )

        response = self.client.get(reverse("blog:live_counts"))
        self.assertEqual(response.status_code, 200)

        search_response = self.client.get(
            reverse("blog:global_search"),
            {"q": "Follow Requests"},
        )
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(
            search_response.json()["navigation"][0]["url"],
            reverse("blog:follow_requests"),
        )

    def test_theme_toggle_is_gated_by_site_setting(self):
        site_settings = SiteSettings.get_cached()
        site_settings.dark_theme_enabled = False
        site_settings.save()

        response = self.client.get(reverse("blog:settings"))
        self.assertNotContains(response, 'id="themeToggle"')
        self.assertNotContains(response, 'name="theme_preference"')
        self.assertContains(response, 'data-theme="light"')

        site_settings.dark_theme_enabled = True
        site_settings.save()
        response = self.client.get(reverse("blog:settings"))
        self.assertContains(response, 'name="theme_preference"')
        self.assertContains(response, 'id="themeToggle"')

    def test_practice_pagination_keeps_active_filters(self):
        for index in range(10):
            PracticeProblem.objects.create(
                slug=f"smoke-page-problem-{index}",
                title=f"Smoke page problem {index}",
                description="Searchable smoke practice problem.",
                difficulty="EASY",
                function_name="solve",
                starter_code={},
                public_tests=[],
                hidden_tests=[],
            )

        response = self.client.get(reverse("blog:practice"), {
            "search": "smoke",
            "difficulty": "easy",
            "page": 2,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["problem_page"].paginator.per_page, 10)
        self.assertEqual(response.context["problem_page"].paginator.count, 11)
        self.assertContains(response, "Showing 11-11 of 11")
        self.assertContains(response, "difficulty=easy&amp;page=1")
        self.assertContains(response, 'name="difficulty"')
        self.assertContains(response, 'value="easy" selected')

    def test_assignment_detail_stays_not_started_until_user_saves(self):
        response = self.client.get(reverse("blog:assignment_attempt", args=(self.assignment.pk,)))
        self.assertEqual(response.status_code, 200)

        progress = UserAssignmentProgress.objects.get(user=self.user, assignment=self.assignment)
        self.assertEqual(progress.status, "NOT_STARTED")
        self.assertEqual(progress.attempts_used, 0)
        self.assertFalse(AssignmentAttempt.objects.filter(assignment=self.assignment, user=self.user).exists())

        response = self.client.post(
            reverse("blog:assignment_attempt", args=(self.assignment.pk,)),
            {"action": "save", "answer_data": "{}"},
        )
        self.assertEqual(response.status_code, 200)
        progress.refresh_from_db()
        self.assertEqual(progress.status, "IN_PROGRESS")
        self.assertEqual(progress.attempts_used, 1)

    def test_goal_descriptions_match_the_selected_learning_goal(self):
        response = self.client.get(reverse("blog:choose_goal"))
        options = {
            option["label"]: option["description"]
            for option in response.context["goal_options"]
        }

        self.assertEqual(
            options["Python Full Stack Developer"],
            "Learn the tools to build complete web applications with Python, Django, JavaScript and SQL.",
        )
        self.assertEqual(options["Django Developer"], "Create powerful web applications with Django.")
        self.assertEqual(options["Data Analyst"], "Analyze data and build reports with Python and SQL.")
        self.assertEqual(
            options["Interview Prep"],
            "Prepare for technical and behavioral interviews and strengthen problem-solving and DSA skills.",
        )
        self.assertEqual(
            options["Web Basics"],
            "Build a solid programming foundation with HTML, CSS, JavaScript and Python basics.",
        )

    def test_problem_set_title_uses_its_active_problem_count(self):
        problem_set = PracticeProblemSet.objects.create(
            title="Interview 50",
            slug="smoke-interview-set",
            active=True,
        )
        problem_set.problems.add(self.problem)

        response = self.client.get(reverse("blog:practice_problem_sets"))

        set_row = next(row for row in response.context["sets"] if row["set"].pk == problem_set.pk)
        self.assertEqual(set_row["display_title"], "Interview 1")
        self.assertContains(response, "Interview 1")

    def test_practice_leaderboard_uses_ten_row_pages_and_theme_surface(self):
        for index in range(11):
            learner = get_user_model().objects.create_user(
                username=f"leader-page-{index}",
                password="test-password",
            )
            PracticeProgress.objects.create(
                user=learner,
                problem=self.problem,
                status="SOLVED",
            )

        response = self.client.get(reverse("blog:practice_leaderboard"), {"period": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["leaderboard"].paginator.per_page, 10)
        self.assertEqual(response.context["leaderboard"].paginator.num_pages, 2)
        self.assertContains(response, "leaderboard-period")
        self.assertContains(response, "leader-avatar")