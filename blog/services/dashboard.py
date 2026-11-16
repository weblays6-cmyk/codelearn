from collections import Counter
from datetime import datetime, time, timedelta
from fractions import Fraction
from urllib.parse import urljoin

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.urls import reverse
from django.utils import timezone

from ..models import (
    Assignment,
    AssignmentSubmission,
    CommunityReply,
    DailyTopPerformer,
    Enrollment,
    Lesson,
    LessonProgress,
    MockTestAttempt,
    Notification,
    Post,
    PracticeProblem,
    PracticeProgress,
    PracticeSubmission,
    StreakFreeze,
    UserProfile,
    UserAssignmentProgress,
    XPEvent,
)

GOAL_CATEGORIES = {
    'full_stack': ('Python', 'Django', 'JavaScript', 'HTML/CSS'),
    'django': ('Django', 'Python'),
    'data': ('SQL', 'Python', 'AI'),
    'interview': ('Python', 'Java', 'C++', 'JavaScript'),
    'web': ('HTML/CSS', 'JavaScript'),
}


def level_for_xp(total_xp):
    level = max(1, total_xp // 100 + 1)
    return {
        'level': level,
        'current': total_xp % 100,
        'next': 100,
        'percent': total_xp % 100,
    }


def award_xp(user, event_type, source_type, source_id, points):
    with transaction.atomic():
        before = XPEvent.objects.filter(user=user, is_verified=True).aggregate(total=Sum('points'))['total'] or 0
        event, created = XPEvent.objects.get_or_create(
            user=user,
            event_type=event_type,
            source_type=source_type,
            source_id=str(source_id),
            defaults={'points': points, 'is_verified': True},
        )
        if not created:
            return event, False
        after = before + event.points
        if level_for_xp(after)['level'] > level_for_xp(before)['level']:
            Notification.objects.create(
                recipient=user,
                sender=user,
                notification_type='LEVEL_UP',
                message=f"You reached level {level_for_xp(after)['level']}!",
            )
        return event, True


def award_daily_mission_if_complete(user, day=None):
    day = day or timezone.localdate(timezone=timezone.get_default_timezone())
    lesson_done = LessonProgress.objects.filter(
        student=user,
        completed=True,
        completed_at__date=day,
    ).exists()
    problem_done = PracticeProgress.objects.filter(
        user=user,
        status='SOLVED',
        solved_at__date=day,
    ).exists()
    if lesson_done and problem_done:
        return award_xp(user, 'DAILY_MISSION', 'date', day.isoformat(), 25)
    return None


def _today_bounds(day):
    tz = timezone.get_default_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    return start, start + timedelta(days=1)


def _public_assignment_submissions(start, end):
    return AssignmentSubmission.objects.filter(
        status='Evaluated',
        evaluated_by__isnull=False,
        evaluated_at__gte=start,
        evaluated_at__lt=end,
        score__isnull=False,
        assignment__max_score__gt=0,
        student__is_staff=False,
        student__is_superuser=False,
        student__profile_data__is_private=False,
        student__profile_data__show_public_badges=True,
        student__profile_data__is_deactivated=False,
        student__profile_data__scheduled_deletion_at__isnull=True,
        student__profile_data__is_test_account=False,
    ).select_related('student__profile_data', 'assignment')


def _leader_tiebreak(submission):
    return (
        Fraction(submission.score, submission.assignment.max_score),
        submission.score,
        -submission.submitted_at.timestamp(),
        -submission.student_id,
    )


def _leader_data(user, assignment, percent):
    name = user.get_full_name().strip() or user.username
    profile = user.profile_data
    return {
        'name': name,
        'username': user.username,
        'avatar': urljoin(settings.SITE_BASE_URL + '/', profile.profile_picture.url)
        if profile.profile_picture else '',
        'initials': ''.join(part[0].upper() for part in name.split()[:2]),
        'percent': min(100, percent),
        'assignment_title': assignment.title,
        'profile_url': reverse('blog:user_profile', args=[user.username]),
    }


def award_daily_leader(day=None):
    day = day or timezone.localdate(timezone=timezone.get_default_timezone())
    cache.delete(f'blog.daily_leader.{day.isoformat()}')
    start, end = _today_bounds(day)
    submissions = list(_public_assignment_submissions(start, end))
    if not submissions:
        cache.set(f'blog.daily_leader.{day.isoformat()}', False, 60)
        return None

    winner = max(submissions, key=_leader_tiebreak)
    percentage = round(winner.score * 100 / winner.assignment.max_score)
    with transaction.atomic():
        badge, created = DailyTopPerformer.objects.update_or_create(
            date=day,
            defaults={
                'user': winner.student,
                'assignment': winner.assignment,
                'submission': winner,
                'score': winner.score,
                'percent': min(100, percentage),
            },
        )
        Notification.objects.get_or_create(
            recipient=winner.student,
            notification_type='DAILY_LEADER',
            dedupe_key=f'daily-leader:{day.isoformat()}',
            defaults={
                'sender': winner.student,
                'message': 'You are today’s top performer!',
            },
        )
    cache.set(
        f'blog.daily_leader.{day.isoformat()}',
        badge.pk,
        60,
    )
    return badge


def _public_leader_queryset(day):
    return DailyTopPerformer.objects.filter(
        date=day,
        user__profile_data__is_private=False,
        user__profile_data__show_public_badges=True,
        user__profile_data__is_deactivated=False,
        user__profile_data__scheduled_deletion_at__isnull=True,
        user__profile_data__is_test_account=False,
        user__is_staff=False,
        user__is_superuser=False,
    ).select_related('user__profile_data', 'assignment')


def today_leader():
    today = timezone.localdate(timezone=timezone.get_default_timezone())
    key = f'blog.daily_leader.{today.isoformat()}'
    badge_id = cache.get(key, ...)
    if badge_id is ...:
        badge = _public_leader_queryset(today).first()
        if not badge:
            badge = award_daily_leader(today)
        else:
            cache.set(key, badge.pk, 60)
    elif badge_id:
        badge = _public_leader_queryset(today).filter(pk=badge_id).first()
        if not badge:
            badge = award_daily_leader(today)
    else:
        badge = None
    if badge:
        return _leader_data(badge.user, badge.assignment, badge.percent)
    return None


def month_leader(today=None):
    today = today or timezone.localdate(timezone=timezone.get_default_timezone())
    month_start = today.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    tz = timezone.get_default_timezone()
    start = timezone.make_aware(datetime.combine(month_start, time.min), tz)
    end = timezone.make_aware(datetime.combine(next_month, time.min), tz)
    key = f'blog.month_leader.{month_start:%Y-%m}'
    cached = cache.get(key, ...)
    if cached is not ...:
        return cached or None

    submissions = list(_public_assignment_submissions(start, end))
    if not submissions:
        cache.set(key, False, 60)
        return None
    winner = max(submissions, key=_leader_tiebreak)
    data = _leader_data(
        winner.student,
        winner.assignment,
        round(winner.score * 100 / winner.assignment.max_score),
    )
    cache.set(key, data, 60)
    return data


def _activity_dates(user):
    dates = set(LessonProgress.objects.filter(
        student=user,
        completed=True,
        completed_at__isnull=False,
    ).dates('completed_at', 'day'))
    dates.update(PracticeSubmission.objects.filter(
        user=user,
        status='ACCEPTED',
    ).dates('submitted_at', 'day'))
    dates.update(MockTestAttempt.objects.filter(
        user=user,
        status__in=('COMPLETED', 'EXPIRED'),
        submitted_at__isnull=False,
    ).dates('submitted_at', 'day'))
    dates.update(AssignmentSubmission.objects.filter(
        student=user,
        status='Evaluated',
        evaluated_at__isnull=False,
    ).dates('evaluated_at', 'day'))
    return dates


def _streak_data(user, activity_dates, apply_freeze=True):
    today = timezone.localdate(timezone=timezone.get_default_timezone())
    cursor = today if today in activity_dates else today - timedelta(days=1)
    streak = 0
    used_freeze_weeks = set()
    freeze_dates = dict(
        StreakFreeze.objects.filter(
            user=user,
            freeze_date__isnull=False,
        ).values_list('week_start', 'freeze_date')
    ) if apply_freeze else {}
    effective_dates = activity_dates | set(freeze_dates.values())
    while True:
        if cursor in effective_dates:
            streak += 1
            cursor -= timedelta(days=1)
            continue
        week_start = cursor - timedelta(days=cursor.weekday())
        if (
            apply_freeze
            and (
                cursor + timedelta(days=1) in effective_dates
                or cursor == today - timedelta(days=1)
            )
            and cursor - timedelta(days=1) in effective_dates
            and week_start not in used_freeze_weeks
        ):
            freeze_date = freeze_dates.get(week_start)
            if freeze_date is None:
                try:
                    StreakFreeze.objects.create(
                        user=user,
                        week_start=week_start,
                        freeze_date=cursor,
                    )
                    freeze_dates[week_start] = cursor
                    effective_dates = effective_dates | {cursor}
                except IntegrityError:
                    freeze_dates[week_start] = StreakFreeze.objects.filter(
                        user=user,
                        week_start=week_start,
                    ).values_list('freeze_date', flat=True).first()
                    freeze_date = freeze_dates[week_start]
                    if freeze_date:
                        effective_dates = effective_dates | {freeze_date}
            if freeze_dates.get(week_start) != cursor:
                break
            streak += 1
            used_freeze_weeks.add(week_start)
            cursor -= timedelta(days=1)
            continue
        break
    ordered = sorted(activity_dates | set(freeze_dates.values()))
    longest = run = 0
    previous = None
    for active_day in ordered:
        run = run + 1 if previous and active_day == previous + timedelta(days=1) else 1
        longest = max(longest, run)
        previous = active_day
    return streak, max(longest, streak)


def badge_case(user, solved=None, longest_streak=None, courses_count=None, course_complete=None):
    profile = user.profile_data
    if solved is None:
        solved = PracticeProgress.objects.filter(user=user, status='SOLVED').count()
    if longest_streak is None:
        _, longest_streak = _streak_data(user, _activity_dates(user), apply_freeze=False)
    if courses_count is None:
        courses_count = Enrollment.objects.filter(student=user).count()
    if course_complete is None:
        course_complete = Enrollment.objects.filter(student=user, completed=True).exists()
    return [
        {'name': 'First Solve', 'unlocked': solved >= 1, 'hint': 'Solve your first practice problem.'},
        {'name': '7-day Streak', 'unlocked': longest_streak >= 7, 'hint': 'Build a 7-day learning streak.'},
        {'name': '30-day Streak', 'unlocked': longest_streak >= 30, 'hint': 'Build a 30-day learning streak.'},
        {'name': '10 Problems', 'unlocked': solved >= 10, 'hint': 'Solve 10 practice problems.'},
        {'name': '50 Problems', 'unlocked': solved >= 50, 'hint': 'Solve 50 practice problems.'},
        {'name': 'First Course', 'unlocked': courses_count > 0, 'hint': 'Enroll in your first course.'},
        {'name': 'Course Complete', 'unlocked': course_complete, 'hint': 'Complete a course.'},
        {'name': 'Profile Complete', 'unlocked': bool(profile.display_name and profile.goal and profile.profile_picture), 'hint': 'Add a name, goal and profile photo.'},
        {'name': 'Daily Leader', 'unlocked': user.daily_leader_wins.exists(), 'hint': 'Earn the Top performer today badge.'},
        {'name': 'Community Helper', 'unlocked': CommunityReply.objects.filter(author=user).exists(), 'hint': 'Help someone by replying to a community question.'},
    ]


def dashboard_data(user):
    today = timezone.localdate(timezone=timezone.get_default_timezone())
    now = timezone.now()
    profile = UserProfile.objects.get(user=user)
    award_xp(user, 'DAILY_LOGIN', 'date', today.isoformat(), 5)
    xp_total = XPEvent.objects.filter(user=user, is_verified=True).aggregate(total=Sum('points'))['total'] or 0
    level = level_for_xp(xp_total)

    enrollments = list(
        Enrollment.objects.filter(student=user)
        .select_related('course')
        .order_by('-last_accessed_at', '-enrolled_at')
    )
    solved = PracticeProgress.objects.filter(user=user, status='SOLVED').count()
    mock_attempts = list(MockTestAttempt.objects.filter(
        user=user,
        status__in=('COMPLETED', 'EXPIRED'),
    ).exclude(total_score=0).values_list('score', 'total_score'))
    assignment_scores = list(AssignmentSubmission.objects.filter(
        student=user,
        status='Evaluated',
        score__isnull=False,
        assignment__max_score__gt=0,
    ).values_list('score', 'assignment__max_score'))
    percentages = [score * 100 / total for score, total in mock_attempts + assignment_scores if total]

    activity_dates = _activity_dates(user)
    streak, longest_streak = _streak_data(user, activity_dates)
    heatmap_start = today - timedelta(days=today.weekday() + 77)
    activity_map = Counter(day for day in activity_dates if day >= heatmap_start)
    activity_counts = Counter()
    for queryset, date_field in (
        (LessonProgress.objects.filter(student=user, completed=True, completed_at__isnull=False), 'completed_at'),
        (PracticeSubmission.objects.filter(user=user, status='ACCEPTED'), 'submitted_at'),
        (MockTestAttempt.objects.filter(user=user, status__in=('COMPLETED', 'EXPIRED'), submitted_at__isnull=False), 'submitted_at'),
        (AssignmentSubmission.objects.filter(student=user, status='Evaluated', evaluated_at__isnull=False), 'evaluated_at'),
    ):
        date_key = f'{date_field}__date'
        activity_counts.update(dict(
            queryset.filter(**{f'{date_field}__date__gte': heatmap_start, f'{date_field}__date__lte': today})
            .values(date_key)
            .annotate(task_count=Count('id'))
            .values_list(date_key, 'task_count')
        ))
    heatmap = [
        {
            'date': heatmap_start + timedelta(days=index),
            'active': (heatmap_start + timedelta(days=index)) in activity_map,
            'count': activity_counts.get(heatmap_start + timedelta(days=index), 0),
            'level': min(4, activity_counts.get(heatmap_start + timedelta(days=index), 0)),
        }
        for index in range(84)
    ]
    heatmap_weeks = []
    for week_index in range(12):
        week_days = heatmap[week_index * 7:(week_index + 1) * 7]
        heatmap_weeks.append({
            'month': next((day['date'].strftime('%b') for day in week_days if day['date'].day == 1), ''),
        })
    week_start = today - timedelta(days=today.weekday())
    previous_week_start = week_start - timedelta(days=7)
    this_week_end = week_start + timedelta(days=7)
    activity_summary = {}
    for label, start_day, end_day in (
        ('this_week', week_start, this_week_end),
        ('last_week', previous_week_start, week_start),
    ):
        start_at, _ = _today_bounds(start_day)
        end_at, _ = _today_bounds(end_day)
        lesson_rows = list(LessonProgress.objects.filter(
            student=user,
            completed=True,
            completed_at__gte=start_at,
            completed_at__lt=end_at,
        ).values_list('started_at', 'completed_at'))
        test_rows = list(MockTestAttempt.objects.filter(
            user=user,
            status__in=('COMPLETED', 'EXPIRED'),
            submitted_at__gte=start_at,
            submitted_at__lt=end_at,
        ).values_list('started_at', 'submitted_at'))
        activity_summary[label] = {
            'lessons': len(lesson_rows),
            'problems': PracticeProgress.objects.filter(
                user=user,
                status='SOLVED',
                solved_at__gte=start_at,
                solved_at__lt=end_at,
            ).count(),
            'minutes': round(sum(
                max(0, min((end - start).total_seconds(), 4 * 60 * 60))
                for start, end in lesson_rows + test_rows
                if start and end
            ) / 60),
        }
    weekday_counts = Counter(day.strftime('%A') for day in activity_dates)
    best_study_day = max(weekday_counts, key=weekday_counts.get) if weekday_counts else 'No activity yet'
    current_week_activity = Counter()
    current_week_activity.update(LessonProgress.objects.filter(
        student=user,
        completed=True,
        completed_at__gte=_today_bounds(week_start)[0],
        completed_at__lt=_today_bounds(this_week_end)[0],
    ).dates('completed_at', 'day'))
    current_week_activity.update(PracticeProgress.objects.filter(
        user=user,
        status='SOLVED',
        solved_at__gte=_today_bounds(week_start)[0],
        solved_at__lt=_today_bounds(this_week_end)[0],
    ).dates('solved_at', 'day'))
    current_week_activity.update(MockTestAttempt.objects.filter(
        user=user,
        status__in=('COMPLETED', 'EXPIRED'),
        submitted_at__gte=_today_bounds(week_start)[0],
        submitted_at__lt=_today_bounds(this_week_end)[0],
    ).dates('submitted_at', 'day'))

    enrolled_ids = [item.course_id for item in enrollments]
    course_lessons = Lesson.objects.filter(
        course_id__in=enrolled_ids,
    ).select_related('course').prefetch_related(
        Prefetch(
            'student_progress',
            queryset=LessonProgress.objects.filter(student=user),
            to_attr='dashboard_progress',
        ),
    ).order_by('course_id', 'order')
    next_lesson_by_course = {}
    for lesson in course_lessons:
        lesson_progress = lesson.dashboard_progress[0] if lesson.dashboard_progress else None
        lesson.last_accessed_at = lesson_progress.last_accessed_at if lesson_progress else None
        if lesson_progress and lesson_progress.completed:
            continue
        if lesson.course_id not in next_lesson_by_course:
            next_lesson_by_course[lesson.course_id] = lesson
    for enrollment in enrollments:
        enrollment.next_lesson = next_lesson_by_course.get(enrollment.course_id)
    goal_categories = GOAL_CATEGORIES.get(profile.goal, ())
    goal_course_ids = [
        item.course_id for item in enrollments
        if not goal_categories or item.course.category in goal_categories
    ] or enrolled_ids
    resume_lesson = max(
        (lesson for lesson in next_lesson_by_course.values() if lesson.last_accessed_at),
        key=lambda lesson: lesson.last_accessed_at,
        default=None,
    ) or next(iter(next_lesson_by_course.values()), None)
    resume_enrollment = next(
        (item for item in enrollments if resume_lesson and item.course_id == resume_lesson.course_id),
        None,
    )

    lessons_today = LessonProgress.objects.filter(
        student=user, completed=True, completed_at__date=today,
    ).count()
    problems_today = PracticeProgress.objects.filter(
        user=user, status='SOLVED', solved_at__date=today,
    ).count()
    daily_task_goal = profile.daily_task_goal if profile.daily_task_goal in (1, 3, 5) else 3
    daily_tasks_done = (
        lessons_today
        + problems_today
        + MockTestAttempt.objects.filter(
            user=user,
            status__in=('COMPLETED', 'EXPIRED'),
            submitted_at__date=today,
        ).count()
        + AssignmentSubmission.objects.filter(
            student=user,
            status='Evaluated',
            evaluated_at__date=today,
        ).count()
    )
    lesson_done_today = lessons_today > 0
    problem_done_today = problems_today > 0
    if lesson_done_today and problem_done_today:
        award_daily_mission_if_complete(user, today)
        xp_total = XPEvent.objects.filter(user=user, is_verified=True).aggregate(total=Sum('points'))['total'] or 0
        level = level_for_xp(xp_total)
    mission_lesson = Lesson.objects.filter(course_id__in=goal_course_ids).exclude(
        student_progress__student=user,
        student_progress__completed=True,
    ).select_related('course').first() if enrolled_ids else None
    problem_categories = {
        'full_stack': ('python', 'django', 'javascript', 'html/css'),
        'django': ('django', 'python'),
        'data': ('sql', 'python'),
        'interview': ('python', 'dsa', 'algorithms'),
        'web': ('html/css', 'javascript'),
    }.get(profile.goal, ())
    problem_queryset = PracticeProblem.objects.filter(active=True)
    if problem_categories:
        problem_queryset = problem_queryset.filter(category__in=problem_categories)
    mission_problem = problem_queryset.exclude(
        progress__user=user, progress__status='SOLVED',
    ).first()

    assignments = list(Assignment.objects.filter(
        status='PUBLISHED',
        due_date__gte=now,
    ).filter(
        Q(course__enrolled_students__student=user)
        | Q(lesson__course__enrolled_students__student=user)
        | Q(audiences__audience_type='ALL_USERS')
        | Q(audiences__audience_type='SELECTED_USER', audiences__user=user)
    ).distinct().select_related('course').order_by('due_date')[:3])
    assignment_progress = {
        row.assignment_id: row.status
        for row in UserAssignmentProgress.objects.filter(
            user=user,
            assignment_id__in=[item.pk for item in assignments],
        )
    }
    for assignment in assignments:
        assignment.display_status = assignment_progress.get(assignment.pk, 'Upcoming').replace('_', ' ').title()
    deadline_counts = Counter(
        timezone.localtime(item.due_date, timezone.get_default_timezone()).date()
        for item in assignments
        if item.due_date
    )
    recent = []
    recent.extend(
        {'title': f'Solved {row.problem.title}', 'created_at': row.submitted_at}
        for row in PracticeSubmission.objects.filter(
            user=user,
            status='ACCEPTED',
        ).select_related('problem')[:5]
    )
    recent.extend(
        {'title': f'Completed {row.lesson.title}', 'created_at': row.completed_at}
        for row in LessonProgress.objects.filter(
            student=user,
            completed=True,
            completed_at__isnull=False,
        ).select_related('lesson')[:5]
    )
    recent.extend(
        {'title': f'Submitted {row.assignment.title}', 'created_at': row.submitted_at}
        for row in AssignmentSubmission.objects.filter(
            student=user,
        ).select_related('assignment')[:5]
    )
    recent.extend(
        {'title': f'Completed {row.test.title}', 'created_at': row.submitted_at}
        for row in MockTestAttempt.objects.filter(
            user=user,
            status__in=('COMPLETED', 'EXPIRED'),
            submitted_at__isnull=False,
        ).select_related('test')[:5]
    )
    recent.sort(key=lambda item: item['created_at'] or now, reverse=True)

    courses_count = len(enrollments)
    skill_counts = Counter()
    for category, title, tags in PracticeProgress.objects.filter(
        user=user,
        status='SOLVED',
    ).values_list('problem__category', 'problem__title', 'problem__tags'):
        searchable = f'{category} {title} {tags}'.lower()
        for skill, keywords in (
            ('Python', ('python',)),
            ('Django', ('django',)),
            ('SQL', ('sql', 'database')),
            ('JS', ('javascript', ' js ')),
            ('HTML/CSS', ('html', 'css', 'web')),
            ('DSA', ('dsa', 'algorithm', 'data structure')),
        ):
            if any(keyword in searchable for keyword in keywords):
                skill_counts[skill] += 1
    for category, title in LessonProgress.objects.filter(
        student=user,
        completed=True,
    ).values_list('lesson__course__category', 'lesson__title'):
        searchable = f'{category} {title}'.lower()
        for skill, keywords in (
            ('Python', ('python',)),
            ('Django', ('django',)),
            ('SQL', ('sql', 'database')),
            ('JS', ('javascript', ' js ')),
            ('HTML/CSS', ('html', 'css', 'web')),
            ('DSA', ('dsa', 'algorithm', 'data structure')),
        ):
            if any(keyword in searchable for keyword in keywords):
                skill_counts[skill] += 1
    skills = [
        {'name': name, 'score': min(100, skill_counts[name] * 20)}
        for name in ('Python', 'Django', 'SQL', 'JS', 'HTML/CSS', 'DSA')
    ]
    roadmap = {
        'full_stack': ('Python', 'HTML/CSS', 'JS', 'Django', 'SQL', 'DSA'),
        'django': ('Python', 'Django', 'SQL', 'HTML/CSS', 'JS', 'DSA'),
        'data': ('Python', 'SQL', 'DSA'),
        'interview': ('DSA', 'Python', 'SQL', 'JS'),
        'web': ('HTML/CSS', 'JS', 'Django', 'Python'),
    }.get(profile.goal, ('Python', 'HTML/CSS', 'JS'))
    roadmap_nodes = [
        {
            'name': node,
            'done': skill_counts[node] > 0,
            'next': skill_counts[node] == 0 and not any(
                skill_counts[prior] == 0 for prior in roadmap[:index]
            ),
        }
        for index, node in enumerate(roadmap)
    ]
    recommendations = list(
        Post.objects.filter(
            status='PUBLISHED',
            category__in=goal_categories,
        ).exclude(pk__in=enrolled_ids).order_by('-created_at')[:3]
    ) if goal_categories else []
    announcements = list(
        Post.objects.filter(
            author__is_staff=True,
            status='PUBLISHED',
        ).order_by('-created_at')[:3]
    )
    badges = badge_case(
        user,
        solved=solved,
        longest_streak=longest_streak,
        courses_count=courses_count,
        course_complete=any(item.completed for item in enrollments),
    )
    today_leader_badge = today_leader()
    return {
        'my_enrollments': enrollments,
        'dashboard_data': {
            'courses_count': courses_count,
            'solved': solved,
            'streak': streak,
            'longest_streak': longest_streak,
            'average_score': round(sum(percentages) / len(percentages)) if percentages else 0,
            'xp': xp_total,
            'level': level,
            'xp_remaining': level['next'] - level['current'],
            'next_level': level['level'] + 1,
            'badges': badges,
            'today_leader': today_leader_badge,
            'leader_wins': user.daily_leader_wins.count(),
            'heatmap': heatmap,
            'heatmap_weeks': heatmap_weeks,
            'has_activity': bool(activity_dates),
            'weekly_activity': [
                {'day': (today - timedelta(days=6 - index)).strftime('%a'),
                 'count': current_week_activity.get(today - timedelta(days=6 - index), 0),
                 'height': min(100, current_week_activity.get(today - timedelta(days=6 - index), 0) * 18 + 8)}
                for index in range(7)
            ],
            'activity_summary': activity_summary,
            'best_study_day': best_study_day,
            'mission_percent': (int(lesson_done_today) + int(problem_done_today)) * 50,
            'mission_lesson': mission_lesson,
            'mission_problem': mission_problem,
            'lesson_done_today': lesson_done_today,
            'problem_done_today': problem_done_today,
            'mission_completed': int(lesson_done_today) + int(problem_done_today),
            'daily_task_goal': daily_task_goal,
            'daily_tasks_done': daily_tasks_done,
            'daily_goal_percent': min(100, round(daily_tasks_done * 100 / daily_task_goal)),
            'weekly_goal_days': sum(count > 0 for count in current_week_activity.values()),
            'weekly_goal_target': 5,
            'weekly_goal_percent': min(100, round(sum(count > 0 for count in current_week_activity.values()) * 100 / 5)),
            'upcoming_assignments': assignments,
            'calendar_strip': [
                {
                    'date': today + timedelta(days=index),
                    'count': deadline_counts.get(today + timedelta(days=index), 0),
                }
                for index in range(7)
            ],
            'resume_lesson': resume_lesson,
            'resume_progress': resume_enrollment.progress if resume_enrollment else 0,
            'recommended_courses': recommendations,
            'skill_radar': skills,
            'roadmap': roadmap_nodes,
            'announcements': announcements,
            'recent_activity': recent[:5],
            'checklist': {
                'goal': bool(profile.goal),
                'course': courses_count > 0,
                'problem': solved > 0,
                'profile': bool(profile.display_name and profile.profile_picture),
            },
            'weekly_leaderboard': _weekly_leaderboard(user),
        },
    }


def _weekly_leaderboard(user):
    local_today = timezone.localdate(timezone=timezone.get_default_timezone())
    monday = local_today - timedelta(days=local_today.weekday())
    since, _ = _today_bounds(monday)
    rows = list(
        XPEvent.objects.filter(
            created_at__gte=since,
            is_verified=True,
            user__profile_data__leaderboard_opt_in=True,
            user__profile_data__is_private=False,
            user__profile_data__is_deactivated=False,
            user__profile_data__scheduled_deletion_at__isnull=True,
            user__is_staff=False,
            user__is_superuser=False,
            user__profile_data__is_test_account=False,
        ).values('user_id', 'user__username', 'user__first_name', 'user__last_name')
        .annotate(xp=Sum('points')).order_by('-xp', 'user_id')[:10]
    )
    my_rank = None
    if (
        user.profile_data.leaderboard_opt_in
        and not user.profile_data.is_private
        and not user.profile_data.is_deactivated
        and not user.profile_data.scheduled_deletion_at
        and not user.profile_data.is_test_account
        and not user.is_staff
        and not user.is_superuser
    ):
        all_rows = XPEvent.objects.filter(
            created_at__gte=since,
            is_verified=True,
            user__profile_data__leaderboard_opt_in=True,
            user__profile_data__is_private=False,
            user__profile_data__is_deactivated=False,
            user__profile_data__scheduled_deletion_at__isnull=True,
            user__profile_data__is_test_account=False,
            user__is_staff=False,
            user__is_superuser=False,
        ).values('user_id').annotate(xp=Sum('points')).order_by('-xp', 'user_id')
        my_rank = next((rank for rank, row in enumerate(all_rows, 1) if row['user_id'] == user.pk), None)
    return {'rows': rows, 'my_rank': my_rank}
