from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from blog.models import (
    Assignment,
    AssignmentSubmission,
    DailyTopPerformer,
    Lesson,
    LessonProgress,
    Notification,
    Post,
    PracticeProblem,
    PracticeProgress,
    XPEvent,
)
from blog.services.dashboard import (
    _activity_dates,
    _streak_data,
    _weekly_leaderboard,
    award_daily_leader,
    award_xp,
    badge_case,
    dashboard_data,
    level_for_xp,
    month_leader,
)
from blog.views import _learning_streak_for_user


class XPAwardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("xp-player", password="pass")

    def test_level_thresholds_and_xp_awards_are_idempotent(self):
        self.assertEqual(level_for_xp(0)["level"], 1)
        self.assertEqual(level_for_xp(99)["level"], 1)
        self.assertEqual(level_for_xp(100)["level"], 2)
        first, created = award_xp(self.user, "LESSON_DONE", "lesson", 12, 25)
        again, created_again = award_xp(self.user, "LESSON_DONE", "lesson", 12, 25)

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(XPEvent.objects.filter(user=self.user).count(), 1)

    def test_badge_rules_unlock_and_keep_higher_thresholds_locked(self):
        badges = {
            badge["name"]: badge
            for badge in badge_case(
                self.user,
                solved=10,
                longest_streak=7,
                courses_count=1,
                course_complete=True,
            )
        }

        self.assertTrue(badges["First Solve"]["unlocked"])
        self.assertTrue(badges["7-day Streak"]["unlocked"])
        self.assertFalse(badges["30-day Streak"]["unlocked"])
        self.assertTrue(badges["10 Problems"]["unlocked"])
        self.assertFalse(badges["50 Problems"]["unlocked"])
        self.assertTrue(badges["First Course"]["unlocked"])
        self.assertTrue(badges["Course Complete"]["unlocked"])

    def test_dashboard_renders_zero_state_and_daily_leader_for_other_users(self):
        viewer = User.objects.create_user("dashboard-viewer", password="pass")
        viewer.profile_data.goal = "django"
        viewer.profile_data.save(update_fields=("goal", "onboarding_completed"))
        assignment = Assignment.objects.create(
            title="Evaluated assessment",
            description="Description",
            max_score=100,
        )
        submission = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=self.user,
            answer="Answer",
            status="Submitted",
        )
        AssignmentSubmission.objects.filter(pk=submission.pk).update(
            status="Evaluated",
            score=85,
            evaluated_by=viewer,
            evaluated_at=timezone.now(),
        )
        submission.refresh_from_db()
        cache.delete(f"blog.daily_leader.{timezone.localdate().isoformat()}")

        client = Client()
        client.force_login(viewer)
        response = client.get(reverse("blog:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'LEADER OF THE DAY')
        self.assertNotContains(response, 'data-leader-strip')
        self.assertNotIn("{{", response.content.decode())
        self.assertNotIn("{%", response.content.decode())
        self.assertEqual(DailyTopPerformer.objects.filter(user=self.user).count(), 1)
        profile_response = client.get(
            reverse("blog:user_profile", args=[self.user.username])
        )
        self.assertEqual(profile_response.status_code, 200)
        self.assertContains(profile_response, "Daily Leader wins")

        self.user.profile_data.goal = "django"
        self.user.profile_data.save(update_fields=("goal", "onboarding_completed"))
        client.force_login(self.user)
        winner_response = client.get(reverse("blog:dashboard"))
        self.assertNotContains(winner_response, "LEADER OF THE DAY")

    def test_dashboard_shows_leader_empty_state(self):
        viewer = User.objects.create_user("dashboard-empty", password="pass")
        viewer.profile_data.goal = "django"
        viewer.profile_data.save(update_fields=("goal", "onboarding_completed"))
        cache.delete(f"blog.daily_leader.{timezone.localdate().isoformat()}")
        self.client.force_login(viewer)

        response = self.client.get(reverse("blog:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "LEADER OF THE DAY")
        self.assertNotContains(response, "Submit assignment")

    def test_my_learning_streak_matches_dashboard_activity_calculation(self):
        today = timezone.localdate(timezone=timezone.get_default_timezone())
        assignment = Assignment.objects.create(
            title="Streak assignment",
            description="Description",
            max_score=100,
        )
        AssignmentSubmission.objects.create(
            assignment=assignment,
            student=self.user,
            answer="Answer",
            status="Evaluated",
            score=90,
            evaluated_at=timezone.make_aware(
                datetime.combine(today, time(12)),
                timezone.get_default_timezone(),
            ),
        )

        dashboard_streak, _ = _streak_data(self.user, _activity_dates(self.user))
        self.assertEqual(_learning_streak_for_user(self.user), dashboard_streak)
        self.assertGreaterEqual(dashboard_streak, 1)

    def test_day_month_endpoint_selects_evaluated_assignment_winners(self):
        evaluator = User.objects.create_user("period-evaluator", password="pass")
        day_user = User.objects.create_user("period-day", password="pass")
        month_user = User.objects.create_user("period-month", password="pass")
        assignment = Assignment.objects.create(
            title="Period assignment",
            description="Description",
            max_score=100,
        )
        leader_day = timezone.localdate(timezone=timezone.get_default_timezone()).replace(day=15)
        timezone_obj = timezone.get_default_timezone()
        day_submission = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=day_user,
            answer="Today",
            status="Evaluated",
            score=82,
            evaluated_by=evaluator,
            evaluated_at=timezone.make_aware(datetime.combine(leader_day, time(12)), timezone_obj),
        )
        month_submission = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=month_user,
            answer="Month",
            status="Evaluated",
            score=95,
            evaluated_by=evaluator,
            evaluated_at=timezone.make_aware(datetime.combine(leader_day.replace(day=2), time(12)), timezone_obj),
        )
        self.client.force_login(evaluator)

        cache.delete(f"blog.daily_leader.{leader_day.isoformat()}")
        cache.delete(f"blog.month_leader.{leader_day:%Y-%m}")
        with patch("blog.services.dashboard.timezone.localdate", return_value=leader_day):
            day_response = self.client.get(reverse("blog:dashboard_leader_data"), {"period": "day"})
            month_response = self.client.get(reverse("blog:dashboard_leader_data"), {"period": "month"})
            month_winner = month_leader()

        self.assertEqual(day_response.status_code, 200)
        self.assertEqual(day_response.json()["leader"]["username"], day_user.username)
        self.assertEqual(month_response.status_code, 200)
        self.assertEqual(month_response.json()["leader"]["username"], month_user.username)
        self.assertEqual(month_response.json()["leader"]["percent"], 95)
        self.assertEqual(month_winner["username"], month_user.username)
        self.assertIsNotNone(day_submission.pk)
        self.assertIsNotNone(month_submission.pk)

    def test_shared_pages_always_include_base_stylesheets_and_html_is_not_cached(self):
        viewer = User.objects.create_user("dashboard-styles", password="pass")
        viewer.profile_data.goal = "django"
        viewer.profile_data.save(update_fields=("goal", "onboarding_completed"))
        self.client.force_login(viewer)
        shared_stylesheets = (
            "css/global.css",
            "css/theme.css",
            "css/readability.css",
            "css/learning_ui.css",
            "css/tokens.css",
            "css/ai-feature-panel.css",
            "css/dashboard.css",
        )

        for url_name in ("dashboard", "my_learning", "practice"):
            response = self.client.get(reverse(f"blog:{url_name}"))
            self.assertEqual(response.status_code, 200, url_name)
            self.assertEqual(response.headers["Cache-Control"], "no-cache")
            html = response.content.decode()
            self.assertIn("/static/css/global.css?v=", html)
            for stylesheet in shared_stylesheets:
                self.assertIn(stylesheet, html, f"{stylesheet} missing from {url_name}")

    def test_leader_selection_requires_evaluation_and_excludes_private_users(self):
        evaluator = User.objects.create_user("badge-evaluator", password="pass")
        public_user = User.objects.create_user("badge-public", password="pass")
        private_user = User.objects.create_user("badge-private", password="pass")
        private_user.profile_data.is_private = True
        private_user.profile_data.save(update_fields=("is_private",))
        opted_out_user = User.objects.create_user("badge-opted-out", password="pass")
        opted_out_user.profile_data.show_public_badges = False
        opted_out_user.profile_data.save(update_fields=("show_public_badges",))
        assignment = Assignment.objects.create(
            title="Daily assignment",
            description="Description",
            max_score=100,
        )
        day = timezone.localdate(timezone=timezone.get_default_timezone())
        evaluated_at = timezone.now()
        public = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=public_user,
            answer="Public",
            status="Submitted",
        )
        private = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=private_user,
            answer="Private",
            status="Submitted",
        )
        opted_out = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=opted_out_user,
            answer="Opted out",
            status="Submitted",
        )
        AssignmentSubmission.objects.filter(pk=public.pk).update(
            status="Evaluated",
            score=80,
            evaluated_by=evaluator,
            evaluated_at=evaluated_at,
        )
        AssignmentSubmission.objects.filter(pk=private.pk).update(
            status="Evaluated",
            score=100,
            evaluated_by=evaluator,
            evaluated_at=evaluated_at,
        )
        AssignmentSubmission.objects.filter(pk=opted_out.pk).update(
            status="Evaluated",
            score=95,
            evaluated_by=evaluator,
            evaluated_at=evaluated_at,
        )
        result = award_daily_leader(day)

        self.assertEqual(result.user_id, public_user.pk)

    def test_unverified_xp_is_excluded_from_opt_in_leaderboard(self):
        opted_in = User.objects.create_user("leader-opted-in", password="pass")
        opted_in.profile_data.leaderboard_opt_in = True
        opted_in.profile_data.save(update_fields=("leaderboard_opt_in",))
        XPEvent.objects.create(
            user=self.user,
            event_type="DAILY_LOGIN",
            source_type="date",
            source_id="today",
            points=1000,
            is_verified=False,
        )
        XPEvent.objects.create(
            user=opted_in,
            event_type="DAILY_LOGIN",
            source_type="date",
            source_id="today",
            points=25,
            is_verified=True,
        )

        result = _weekly_leaderboard(self.user)

        self.assertEqual([row["user_id"] for row in result["rows"]], [opted_in.pk])

    def test_leader_ties_use_raw_score_then_earlier_submission_then_user_id(self):
        evaluator = User.objects.create_user("tie-evaluator", password="pass")
        users = [
            User.objects.create_user(f"tie-user-{index}", password="pass")
            for index in range(3)
        ]
        low_raw_assignment = Assignment.objects.create(
            title="Lower raw score",
            description="Description",
            max_score=100,
        )
        tied_assignment = Assignment.objects.create(
            title="Higher raw score",
            description="Description",
            max_score=200,
        )
        submissions = [
            AssignmentSubmission(
                assignment=low_raw_assignment,
                student=users[0],
                answer="",
                status="Evaluated",
                score=90,
                evaluated_by=evaluator,
                evaluated_at=timezone.now(),
            ),
            AssignmentSubmission(
                assignment=tied_assignment,
                student=users[1],
                answer="",
                status="Evaluated",
                score=180,
                evaluated_by=evaluator,
                evaluated_at=timezone.now(),
            ),
            AssignmentSubmission(
                assignment=tied_assignment,
                student=users[2],
                answer="",
                status="Evaluated",
                score=180,
                evaluated_by=evaluator,
                evaluated_at=timezone.now(),
            ),
            AssignmentSubmission(
                assignment=tied_assignment,
                student=users[0],
                answer="",
                status="Evaluated",
                score=180,
                evaluated_by=evaluator,
                evaluated_at=timezone.now(),
            ),
        ]
        AssignmentSubmission.objects.bulk_create(submissions)
        day_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        AssignmentSubmission.objects.filter(student=users[1]).update(
            submitted_at=day_start + timedelta(hours=11),
        )
        AssignmentSubmission.objects.filter(student=users[2]).update(
            submitted_at=day_start + timedelta(hours=10),
        )
        AssignmentSubmission.objects.filter(pk=submissions[3].pk).update(
            submitted_at=day_start + timedelta(hours=10, seconds=1),
        )

        result = award_daily_leader(timezone.localdate())

        self.assertEqual(result.user_id, users[2].pk)
        AssignmentSubmission.objects.filter(pk=submissions[3].pk).update(
            submitted_at=day_start + timedelta(hours=10),
        )
        result = award_daily_leader(timezone.localdate())
        self.assertEqual(result.user_id, users[0].pk)

    def test_leader_requires_evaluated_status_and_an_evaluator(self):
        evaluator = User.objects.create_user("not-evaluator", password="pass")
        assignment = Assignment.objects.create(
            title="Pending assignment",
            description="Description",
            max_score=100,
        )
        submitted = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=self.user,
            answer="Pending",
            status="Submitted",
        )
        AssignmentSubmission.objects.filter(pk=submitted.pk).update(
            score=100,
            evaluated_by=evaluator,
            evaluated_at=timezone.now(),
        )

        self.assertIsNone(award_daily_leader())

        AssignmentSubmission.objects.filter(pk=submitted.pk).update(
            status="Evaluated",
            evaluated_by=None,
        )
        self.assertIsNone(award_daily_leader())

    def test_streak_freeze_bridges_only_one_missed_day_in_a_week(self):
        from unittest.mock import patch

        today = date(2025, 4, 10)
        activity = {
            today,
            today - timedelta(days=2),
            today - timedelta(days=3),
        }
        with patch("blog.services.dashboard.timezone.localdate", return_value=today):
            current, longest = _streak_data(self.user, activity)

        self.assertEqual(current, 4)
        self.assertEqual(longest, 4)

    def test_mission_completion_uses_completed_lesson_and_solved_problem(self):
        self.user.profile_data.goal = "django"
        self.user.profile_data.save(update_fields=("goal",))
        course = Post.objects.create(
            author=self.user,
            title="Mission course",
            content="Course content",
        )
        lesson = Lesson.objects.create(
            course=course,
            title="Mission lesson",
            content="Lesson content",
        )
        problem = PracticeProblem.objects.create(
            slug="mission-problem",
            title="Mission problem",
            description="Practice problem",
            difficulty="EASY",
            function_name="solve",
            starter_code={},
            public_tests=[],
            hidden_tests=[],
        )
        LessonProgress.objects.create(
            student=self.user,
            lesson=lesson,
            completed=True,
            completed_at=timezone.now(),
        )
        PracticeProgress.objects.create(
            user=self.user,
            problem=problem,
            status="SOLVED",
            solved_at=timezone.now(),
        )

        result = dashboard_data(self.user)["dashboard_data"]

        self.assertEqual(result["mission_completed"], 2)
        self.assertTrue(XPEvent.objects.filter(
            user=self.user,
            event_type="DAILY_MISSION",
        ).exists())

    def test_daily_leader_command_is_idempotent_and_keeps_past_days(self):
        evaluator = User.objects.create_user("command-evaluator", password="pass")
        assignment = Assignment.objects.create(
            title="Daily assignment",
            description="Description",
            max_score=100,
        )
        submission = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=self.user,
            answer="Answer",
            status="Submitted",
        )
        AssignmentSubmission.objects.filter(pk=submission.pk).update(
            status="Evaluated",
            score=90,
            evaluated_by=evaluator,
            evaluated_at=timezone.now(),
        )

        call_command("award_daily_leader")
        call_command("award_daily_leader")

        self.assertEqual(DailyTopPerformer.objects.count(), 1)
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.user,
                notification_type="DAILY_LEADER",
            ).count(),
            1,
        )
        yesterday = timezone.localdate() - timedelta(days=1)
        self.assertIsNone(award_daily_leader(yesterday))
        self.assertEqual(DailyTopPerformer.objects.count(), 1)

    def test_next_day_creates_a_new_daily_leader_record(self):
        evaluator = User.objects.create_user("tomorrow-evaluator", password="pass")
        assignment = Assignment.objects.create(
            title="Tomorrow assignment",
            description="Description",
            max_score=100,
        )
        submission = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=self.user,
            answer="Answer",
            status="Submitted",
        )
        tomorrow = timezone.localdate() + timedelta(days=1)
        tomorrow_start = timezone.make_aware(
            datetime.combine(tomorrow, time.min),
            timezone.get_default_timezone(),
        )
        AssignmentSubmission.objects.filter(pk=submission.pk).update(
            status="Evaluated",
            score=70,
            evaluated_by=evaluator,
            evaluated_at=tomorrow_start + timedelta(hours=1),
        )

        result = award_daily_leader(tomorrow)

        self.assertEqual(result.date, tomorrow)
        self.assertEqual(DailyTopPerformer.objects.count(), 1)
