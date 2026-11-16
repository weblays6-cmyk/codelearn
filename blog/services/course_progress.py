import uuid

from django.db.models import Q
from django.utils import timezone

from ..models import (
    Assignment,
    CourseCertificate,
    Enrollment,
    LessonProgress,
    UserAssignmentProgress,
)


def refresh_enrollment_progress(student, course):
    """Recalculate one enrollment from persisted lesson and assignment progress."""
    enrollment = Enrollment.objects.get(student=student, course=course)
    lesson_ids = course.lessons.values_list('id', flat=True)
    lesson_total = len(lesson_ids)
    completed_lessons = LessonProgress.objects.filter(
        student=student,
        lesson_id__in=lesson_ids,
        completed=True,
    ).count()

    required_assignments = Assignment.objects.filter(
        Q(course=course) | Q(lesson__course=course),
        assignment_source='COURSE',
        required=True,
    ).distinct()
    assignment_total = required_assignments.count()
    passed_assignments = UserAssignmentProgress.objects.filter(
        user=student,
        assignment__in=required_assignments,
        status='PASSED',
    ).count()

    requirement_total = lesson_total + assignment_total
    requirement_completed = completed_lessons + passed_assignments
    progress = round(requirement_completed * 100 / requirement_total) if requirement_total else 0
    completed = (
        requirement_total > 0
        and completed_lessons == lesson_total
        and passed_assignments == assignment_total
    )

    enrollment.progress = min(progress, 100)
    enrollment.completed = completed
    enrollment.status = 'COMPLETED' if completed else ('IN_PROGRESS' if requirement_completed else 'ENROLLED')
    if completed:
        enrollment.completed_at = enrollment.completed_at or timezone.now()
        enrollment.certificate_code = enrollment.certificate_code or str(uuid.uuid4())
    else:
        enrollment.completed_at = None
    update_fields = ['progress', 'completed', 'status', 'completed_at']
    if completed:
        update_fields.append('certificate_code')
    enrollment.save(update_fields=update_fields)
    if completed:
        CourseCertificate.objects.get_or_create(enrollment=enrollment)
    return enrollment


def refresh_progress_for_assignment(user, assignment):
    """Refresh the course enrollment affected by a course assignment."""
    course = assignment.course or (assignment.lesson.course if assignment.lesson else None)
    if not course:
        return None
    enrollment = Enrollment.objects.filter(student=user, course=course).first()
    if not enrollment:
        return None
    return refresh_enrollment_progress(user, course)


def mark_lesson_completed(student, lesson):
    progress, _ = LessonProgress.objects.get_or_create(
        student=student,
        lesson=lesson,
    )
    progress.completed = True
    progress.started_at = progress.started_at or timezone.now()
    progress.last_accessed_at = timezone.now()
    progress.completed_at = progress.completed_at or timezone.now()
    progress.save(update_fields=('completed', 'started_at', 'last_accessed_at', 'completed_at'))
    return refresh_enrollment_progress(student, lesson.course)


def has_active_premium(student, now=None):
    profile = getattr(student, 'profile_data', None)
    if not profile or profile.plan != 'premium':
        return False
    now = now or timezone.now()
    return profile.plan_expires_at is None or profile.plan_expires_at > now


def can_access_course(student, course):
    if course.access != 'paid':
        return True
    if not has_active_premium(student):
        return False
    required_plan_id = getattr(course, 'required_plan_id', None)
    profile = getattr(student, 'profile_data', None)
    return not required_plan_id or bool(profile and profile.subscription_plan_id == required_plan_id)


def can_access_lesson(student, lesson):
    if not Enrollment.objects.filter(student=student, course=lesson.course).exists():
        return False
    if lesson.level == 'advanced':
        if not has_active_premium(student) or not can_access_course(student, lesson.course):
            return False
    if not lesson.course.sequential_learning:
        return True
    earlier_lessons = lesson.course.lessons.filter(order__lt=lesson.order)
    if not earlier_lessons.exists():
        return True
    completed_ids = LessonProgress.objects.filter(
        student=student,
        lesson__in=earlier_lessons,
        completed=True,
    ).values_list('lesson_id', flat=True)
    return not earlier_lessons.exclude(id__in=completed_ids).exists()


def start_lesson(student, lesson):
    now = timezone.now()
    progress, _ = LessonProgress.objects.get_or_create(student=student, lesson=lesson)
    progress.started_at = progress.started_at or now
    progress.last_accessed_at = now
    progress.save(update_fields=('started_at', 'last_accessed_at'))
    enrollment = Enrollment.objects.get(student=student, course=lesson.course)
    enrollment.started_at = enrollment.started_at or now
    enrollment.last_accessed_at = now
    enrollment.status = 'IN_PROGRESS' if not enrollment.completed else 'COMPLETED'
    enrollment.save(update_fields=('started_at', 'last_accessed_at', 'status'))
    return progress
