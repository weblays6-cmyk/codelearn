from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from blog.models import (
    AssignmentSubmission,
    MessageAttachment,
    Post,
    ProjectImage,
    UserProfile,
)


class Command(BaseCommand):
    help = (
        'Permanently delete accounts whose 30-day deletion grace period expired. '
        'Schedule `python manage.py purge_scheduled_accounts` to run daily in '
        'production (for example, with Windows Task Scheduler or cron).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='List accounts eligible for deletion without deleting them.',
        )

    def _user_files(self, user, profile):
        files = []
        if profile.profile_picture:
            files.append((profile.profile_picture.storage, profile.profile_picture.name))

        for file_field in (
            Post.objects.filter(author=user).values_list('image', flat=True),
            ProjectImage.objects.filter(project__owner=user).values_list('image', flat=True),
            AssignmentSubmission.objects.filter(student=user).values_list('file', flat=True),
            MessageAttachment.objects.filter(
                Q(message__conversation__project_owner=user)
                | Q(message__conversation__participant=user)
            ).values_list('file', flat=True),
        ):
            for name in file_field.iterator():
                if name:
                    files.append((default_storage, name))
        return files

    def handle(self, *args, **options):
        now = timezone.now()
        candidates = UserProfile.objects.filter(
            scheduled_deletion_at__lte=now,
            deletion_requested_at__isnull=False,
        ).select_related('user')

        if options['dry_run']:
            for profile in candidates.iterator():
                self.stdout.write(
                    f'Would permanently delete @{profile.user.username} (user {profile.user_id}).'
                )
            self.stdout.write(f'{candidates.count()} account(s) eligible.')
            return

        deleted_count = 0
        candidate_ids = list(candidates.values_list('pk', flat=True))
        for candidate_id in candidate_ids:
            with transaction.atomic():
                profile = UserProfile.objects.select_for_update().filter(
                    pk=candidate_id,
                    scheduled_deletion_at__lte=timezone.now(),
                    deletion_requested_at__isnull=False,
                ).select_related('user').first()
                if profile is None:
                    continue

                username = profile.user.username
                files = self._user_files(profile.user, profile)
                profile.user.delete()

            for storage, name in files:
                try:
                    storage.delete(name)
                except OSError as error:
                    self.stderr.write(
                        self.style.WARNING(
                            f'Could not remove media {name} for @{username}: {error}'
                        )
                    )
            deleted_count += 1
            self.stdout.write(f'Permanently deleted @{username}.')

        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted_count} account(s).'))
