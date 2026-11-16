from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from blog.models import Assignment, AssignmentAudience


SAMPLE_ASSIGNMENTS = (
    ('Build a Personal Portfolio', 'Create a responsive portfolio page and describe your design decisions.', 3),
    ('Python Data Cleanup', 'Write a small Python program that validates and cleans a CSV dataset.', 5),
    ('SQL Reporting Queries', 'Use aggregate queries and joins to answer a set of reporting questions.', 7),
    ('Django Notes App', 'Design a small Django notes workflow with validation and access control.', 10),
    ('JavaScript Interactive Form', 'Build an accessible form with client-side validation and clear feedback.', 14),
)


class Command(BaseCommand):
    help = 'Create five sample standalone assignments without duplicating existing records.'

    def handle(self, *args, **options):
        created = 0
        for title, description, days_until_due in SAMPLE_ASSIGNMENTS:
            assignment, was_created = Assignment.objects.get_or_create(
                title=title,
                assignment_source='STANDALONE',
                defaults={
                    'description': description,
                    'instructions': description,
                    'assignment_type': 'PROJECT',
                    'difficulty': 'Beginner',
                    'due_date': timezone.now() + timedelta(days=days_until_due),
                    'max_score': 100,
                    'status': 'PUBLISHED',
                },
            )
            created += int(was_created)
            if not assignment.audiences.filter(audience_type='ALL_USERS').exists():
                AssignmentAudience.objects.create(
                    assignment=assignment,
                    audience_type='ALL_USERS',
                )
        self.stdout.write(self.style.SUCCESS(f'Created {created} sample assignments.'))
