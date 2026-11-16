# vGrowHub

vGrowHub is a Django learning community with courses, lessons, practice problems, browser-based coding exercises, assignments, AI-assisted learning, projects, community discussions, profiles, and notifications.

## Management commands

- `seed_courses` loads the starter course catalog.
- `seed_problems` idempotently loads practice problems.
- `award_daily_leader` calculates daily leader awards.
- `send_due_reminders` creates due-soon assignment notifications without sending duplicates.
- `seed_assignments` loads sample assignments.

Run a command with `python manage.py <command>`.

## Environment variables

- `GEMINI_API_KEY`: provider credential for AI features. Keep it in the deployment environment, never in source control.
- `AI_MODEL_FAST`, `AI_MODEL_BALANCED`, `AI_MODEL_DEEP`: model names for the AI Tutor depth settings.
- `CODE_RUNNER_URL`: optional external Judge0-compatible endpoint for Java, C, and C++. Those languages should remain unavailable when this is unset. Python, JavaScript, SQL, and HTML/CSS/JS exercises run in the browser.
- `DJANGO_SECRET_KEY`: production Django secret.
- `DJANGO_DEBUG`: set to `false` in production.
- `DJANGO_ALLOWED_HOSTS`: comma-separated production hostnames.

AI features require both a configured provider and enabled `SiteSettings` flags. AI-generated advice is not an official assignment grade and is never posted to community pages automatically.

## Deployment checklist

1. Configure secrets and environment-specific settings.
2. Back up the database before upgrading.
3. Run `python manage.py migrate`.
4. Run `python manage.py collectstatic --noinput`.
5. Configure HTTPS, allowed hosts, static/media storage, and a production WSGI/ASGI server.
6. Run `python manage.py check --deploy` and the test suite.

## Development checks

Run `python manage.py check`, `python manage.py makemigrations --check --dry-run`, and `python manage.py test` before deploying.
