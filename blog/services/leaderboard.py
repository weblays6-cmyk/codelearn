from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone

from blog.models import MockTestAttempt, PracticeProgress


DIFFICULTY_POINTS = {'EASY': 10, 'MEDIUM': 20, 'HARD': 30}


def leaderboard_rows(period='all'):
    now = timezone.now()
    if period == 'week':
        cutoff = now - timedelta(days=7)
    elif period == 'month':
        cutoff = now - timedelta(days=30)
    else:
        cutoff = None
        period = 'all'

    points_by_user = defaultdict(int)
    solved_by_user = defaultdict(int)
    tests_by_user = defaultdict(int)

    solved_problems = PracticeProgress.objects.filter(status='SOLVED').select_related('user', 'problem')
    if cutoff:
        solved_problems = solved_problems.filter(solved_at__gte=cutoff)
    for progress in solved_problems:
        points_by_user[progress.user_id] += DIFFICULTY_POINTS.get(progress.problem.difficulty, 10)
        solved_by_user[progress.user_id] += 1

    test_attempts = MockTestAttempt.objects.filter(
        status__in=('COMPLETED', 'EXPIRED'),
        submitted_at__isnull=False,
    ).select_related('test')
    if cutoff:
        test_attempts = test_attempts.filter(submitted_at__gte=cutoff)

    best_test_scores = {}
    for attempt in test_attempts:
        key = (attempt.user_id, attempt.test_id)
        previous = best_test_scores.get(key)
        if previous is None or attempt.score > previous[0]:
            best_test_scores[key] = (attempt.score, attempt.total_score)
    test_percentages = defaultdict(list)
    for (user_id, _test_id), (score, total_score) in best_test_scores.items():
        points_by_user[user_id] += score
        tests_by_user[user_id] += 1
        if total_score:
            test_percentages[user_id].append(round(score * 100 / total_score, 1))

    user_ids = set(points_by_user) | set(solved_by_user) | set(tests_by_user)
    users = User.objects.filter(id__in=user_ids).order_by('username')
    rows = [
        {
            'user': user,
            'points': points_by_user[user.id],
            'solved': solved_by_user[user.id],
            'tests': tests_by_user[user.id],
            'score': round(sum(test_percentages[user.id]) / len(test_percentages[user.id]), 1) if test_percentages[user.id] else 0,
        }
        for user in users
    ]
    rows.sort(key=lambda row: (-row['points'], -row['solved'], row['user'].username.lower()))
    return rows, period
