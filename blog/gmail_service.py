from django.conf import settings
from django.core.mail import send_mail


def send_gmail(to_email, subject, body):
    return send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )