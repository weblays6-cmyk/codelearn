from django.core.management.base import BaseCommand

from blog.services.dashboard import award_daily_leader


class Command(BaseCommand):
    help = "Award today's Daily Leadership Badge from evaluated assignments."

    def handle(self, *args, **options):
        badge = award_daily_leader()
        if badge:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Awarded {badge.user.username} for {badge.date} ({badge.percent}%)."
                )
            )
        else:
            self.stdout.write("No eligible evaluated assignment submissions today.")
