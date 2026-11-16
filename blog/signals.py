import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .gmail_service import send_gmail
from .device_sessions import device_label_from_user_agent, register_device_session
from .models import (
    AssignmentSubmission,
    AssignmentAttempt,
    Assignment,
    AssignmentAudience,
    Enrollment,
    Notification,
    LessonProgress,
    LoginHistory,
    MockTestAttempt,
    PracticeProgress,
    UserProfile,
    UserSession,
)
from .session_security import (
    register_successful_login,
    remove_logged_out_session,
)

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Assignment, dispatch_uid='blog.assignment_published_previous_state')
def remember_assignment_published_state(sender, instance, **kwargs):
    instance._was_published = sender.objects.filter(pk=instance.pk, status='PUBLISHED').exists() if instance.pk else False


def _send_assignment_notifications(assignment, recipient_ids):
    recipient_ids = list(recipient_ids)
    if not recipient_ids:
        return
    sender_user = assignment.created_by or User.objects.filter(pk=recipient_ids[0], is_active=True).first()
    if not sender_user:
        return
    Notification.objects.bulk_create([
        Notification(
            recipient_id=recipient_id,
            notification_type='ASSIGNMENT_NEW',
            dedupe_key=f'assignment-new:{assignment.pk}',
            sender=sender_user,
            message=f'New assignment available: {assignment.title}'[:255],
        )
        for recipient_id in recipient_ids
    ], ignore_conflicts=True, batch_size=500)

@receiver(post_save, sender=Assignment, dispatch_uid='blog.notify_assignment_published')
def notify_assignment_published(sender, instance, created, **kwargs):
    if instance.status != 'PUBLISHED' or getattr(instance, '_was_published', False):
        return
    if instance.assignment_source == 'STANDALONE':
        audience = instance.audiences.all()
        recipient_ids = set()
        if audience.filter(audience_type='ALL_USERS').exists():
            recipient_ids.update(User.objects.filter(is_active=True).values_list('id', flat=True))
        recipient_ids.update(audience.filter(audience_type='SELECTED_USER', user__is_active=True).values_list('user_id', flat=True))
    else:
        course_id = instance.course_id or (instance.lesson.course_id if instance.lesson_id else None)
        recipient_ids = set(Enrollment.objects.filter(course_id=course_id, student__is_active=True).values_list('student_id', flat=True)) if course_id else set()
    _send_assignment_notifications(instance, recipient_ids)


@receiver(post_save, sender=AssignmentAudience, dispatch_uid='blog.notify_assignment_audience_added')
def notify_assignment_audience_added(sender, instance, created, **kwargs):
    if not created or instance.assignment.status != 'PUBLISHED':
        return
    if instance.audience_type == 'ALL_USERS':
        recipient_ids = User.objects.filter(is_active=True).values_list('id', flat=True)
    elif instance.audience_type == 'SELECTED_USER' and instance.user_id and instance.user.is_active:
        recipient_ids = [instance.user_id]
    else:
        return
    _send_assignment_notifications(instance.assignment, recipient_ids)


@receiver(
    user_logged_in,
    dispatch_uid='blog.register_device_session',
)
def register_login_device(sender, request, user, **kwargs):
    register_device_session(
        request,
        user,
        enforce_limit=not getattr(request, '_vgh_session_replacement', False),
    )
    from .services.dashboard import award_xp

    local_day = timezone.localdate(timezone=timezone.get_default_timezone())
    award_xp(user, 'DAILY_LOGIN', 'date', local_day.isoformat(), 5)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    ip = request.META.get('REMOTE_ADDR') or None
    LoginHistory.objects.create(
        user=user,
        device_label=device_label_from_user_agent(user_agent),
        ip=ip,
    )
    older_history_ids = LoginHistory.objects.filter(
        user=user,
    ).order_by('-created_at', '-pk').values_list('pk', flat=True)[10:]
    LoginHistory.objects.filter(pk__in=older_history_ids).delete()


@receiver(
    user_logged_out,
    dispatch_uid='blog.deactivate_logged_out_device',
)
def deactivate_logout_device(sender, request, user, **kwargs):
    session_key = request.session.session_key if request else None
    if session_key:
        UserSession.objects.filter(
            user=user,
            session_key=session_key,
            is_active=True,
        ).update(is_active=False)


@receiver(
    user_logged_in,
    dispatch_uid='blog.register_tracked_login_session',
)
def register_tracked_login_session(sender, request, user, **kwargs):
    register_successful_login(sender, request, user, **kwargs)


@receiver(
    user_logged_out,
    dispatch_uid='blog.remove_tracked_login_session',
)
def remove_tracked_login_session(sender, request, user, **kwargs):
    remove_logged_out_session(sender, request, user, **kwargs)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        display_name = instance.get_full_name().strip() or instance.username
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                'display_name': display_name,
                'onboarding_completed': False,
            },
        )


@receiver(post_save, sender=LessonProgress)
def award_lesson_xp(sender, instance, **kwargs):
    if instance.completed:
        from .services.dashboard import award_daily_mission_if_complete, award_xp

        award_xp(instance.student, 'LESSON_DONE', 'lesson', instance.lesson_id, 25)
        award_daily_mission_if_complete(instance.student)


@receiver(post_save, sender=PracticeProgress)
def award_problem_xp(sender, instance, **kwargs):
    if instance.status == 'SOLVED':
        from .services.dashboard import award_daily_mission_if_complete, award_xp

        award_xp(instance.user, 'FIRST_PROBLEM_SOLVE', 'problem', instance.problem_id, 20)
        award_daily_mission_if_complete(instance.user)


@receiver(post_save, sender=AssignmentSubmission)
def award_assignment_xp_and_leader(sender, instance, **kwargs):
    from .services.dashboard import award_xp, award_daily_leader

    award_xp(
        instance.student,
        'ASSIGNMENT_SUBMITTED',
        'assignment_submission',
        instance.pk,
        15,
    )
    if instance.status == 'Evaluated' and instance.evaluated_by_id and instance.evaluated_at:
        award_xp(
            instance.student,
            'ASSIGNMENT_EVALUATED',
            'assignment_submission',
            instance.pk,
            30,
        )
        award_daily_leader(timezone.localdate(
            instance.evaluated_at,
            timezone=timezone.get_default_timezone(),
        ))


@receiver(post_save, sender=AssignmentAttempt)
def award_quiz_assignment_xp(sender, instance, **kwargs):
    if (
        instance.status == 'EVALUATED'
        and instance.assignment.assignment_type == 'QUIZ'
        and instance.evaluated_at
    ):
        from .services.dashboard import award_xp

        award_xp(instance.user, 'ASSIGNMENT_SUBMITTED', 'assignment_attempt', instance.pk, 15)
        award_xp(instance.user, 'ASSIGNMENT_EVALUATED', 'assignment_attempt', instance.pk, 30)


@receiver(post_save, sender=MockTestAttempt)
def award_mock_test_xp(sender, instance, **kwargs):
    if instance.status in ('COMPLETED', 'EXPIRED') and instance.submitted_at:
        from .services.dashboard import award_xp

        award_xp(instance.user, 'MOCK_TEST', 'mock_test_attempt', instance.pk, 20)


@receiver(
    user_logged_in,
    dispatch_uid='blog.send_vgrowhub_login_notification',
)
def send_login_notification(sender, request, user, **kwargs):
    if getattr(request, '_vgh_login_notification_sent', False):
        return
    request._vgh_login_notification_sent = True

    login_method = request.session.pop('_vgh_login_method', None)
    if not login_method:
        login_method = (
            'Google'
            if '/google/' in request.path.lower()
            else 'Account'
        )
    if not user.email:
        logger.info(
            'Login notification skipped for user %s because no email is configured.',
            user.pk,
        )
        return

    try:
        send_gmail(
            user.email,
            'New login to your vGrowHub account',
            f"""Hello @{user.username},

Your vGrowHub account was successfully logged in.

Username: @{user.username}
Login method: {login_method}
Login time: {timezone.localtime().strftime("%B %d, %Y at %I:%M %p %Z")}

If this was not you, please secure your account.

Regards,
vGrowHub Team
""",
        )
    except Exception:
        logger.exception(
            'vGrowHub login alert email delivery failed for user %s.',
            user.pk,
        )
