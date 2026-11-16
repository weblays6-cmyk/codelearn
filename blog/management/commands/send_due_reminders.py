from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from blog.models import Assignment, Enrollment, Notification

User = get_user_model()


class Command(BaseCommand):
    help = 'Send idempotent assignment due-soon reminders for deadlines within 24 hours.'

    def handle(self, *args, **options):
        now = timezone.now()
        assignments = Assignment.objects.filter(
            status='PUBLISHED',
            due_date__gt=now,
            due_date__lte=now + timedelta(hours=24),
        ).select_related('course', 'lesson__course', 'created_by').prefetch_related('audiences')
        created = 0
        for assignment in assignments:
            if assignment.assignment_source == 'STANDALONE':
                audiences = assignment.audiences.all()
                if audiences.filter(audience_type='ALL_USERS').exists():
                    recipients = User.objects.filter(is_active=True)
                else:
                    user_ids = audiences.filter(audience_type='SELECTED_USER').values_list('user_id', flat=True)
                    recipients = User.objects.filter(pk__in=user_ids, is_active=True)
            else:
                course_id = assignment.course_id or (assignment.lesson.course_id if assignment.lesson_id else None)
                recipients = User.objects.filter(enrollments__course_id=course_id, is_active=True).distinct() if course_id else User.objects.none()
            recipient_ids = list(recipients.values_list('pk', flat=True))
            if not recipient_ids:
                continue
            sender = assignment.created_by or User.objects.filter(pk=recipient_ids[0]).first()
            if not sender:
                continue
            dedupe_keys = [f'assignment-due:{assignment.pk}:{recipient_id}' for recipient_id in recipient_ids]
            existing_keys = set(Notification.objects.filter(
                recipient_id__in=recipient_ids,
                notification_type='ASSIGNMENT_DUE',
                dedupe_key__in=dedupe_keys,
            ).values_list('dedupe_key', flat=True))
            pending = [
                Notification(
                    recipient_id=recipient_id,
                    notification_type='ASSIGNMENT_DUE',
                    dedupe_key=f'assignment-due:{assignment.pk}:{recipient_id}',
                    sender=sender,
                    message=f'"{assignment.title}" is due within 24 hours.'[:255],
                )
                for recipient_id in recipient_ids
                if f'assignment-due:{assignment.pk}:{recipient_id}' not in existing_keys
            ]
            Notification.objects.bulk_create(pending, ignore_conflicts=True, batch_size=500)
            created += len(pending)
        self.stdout.write(self.style.SUCCESS(f'Created {created} due reminders.'))
