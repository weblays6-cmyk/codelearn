from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def site_base_url():
    configured = getattr(settings, 'SITE_BASE_URL', '').strip()
    if configured:
        return configured.rstrip('/')
    if settings.DEBUG:
        return 'http://127.0.0.1:8000'
    return 'https://vgrowhub.hopto.org'


def build_site_url(path=''):
    base_url = site_base_url().rstrip('/')
    if not path:
        return base_url
    return urljoin(f'{base_url}/', path.lstrip('/'))


def send_gmail(to_email, subject, body, html_body=None):
    email = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    if html_body is not None:
        email.attach_alternative(html_body, 'text/html')
    return email.send(fail_silently=False)