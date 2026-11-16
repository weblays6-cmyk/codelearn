import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import Notification, Payment, UserProfile


class PaymentsUnavailable(Exception):
    pass


class RazorpayProvider:
    name = 'razorpay'

    def __init__(self):
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET

    @property
    def configured(self):
        return bool(self.key_id and self.key_secret)

    def create_order(self, payment):
        if not self.configured:
            raise PaymentsUnavailable
        try:
            import razorpay
        except ImportError as error:
            raise PaymentsUnavailable from error
        client = razorpay.Client(auth=(self.key_id, self.key_secret))
        return client.order.create(data={
            'amount': int(payment.amount * 100),
            'currency': payment.currency,
            'receipt': f'payment-{payment.pk}',
            'notes': {'payment_id': str(payment.pk)},
        })

    def verify_payment_signature(self, order_id, payment_id, signature):
        if not self.key_secret or not order_id or not payment_id or not signature:
            return False
        message = f'{order_id}|{payment_id}'.encode('utf-8')
        expected = hmac.new(
            self.key_secret.encode('utf-8'),
            message,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_webhook_signature(self, body, signature):
        if not self.webhook_secret or not signature:
            return False
        expected = hmac.new(
            self.webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


@transaction.atomic
def complete_payment(payment, provider_id):
    payment = Payment.objects.select_for_update().select_related('user', 'plan').get(pk=payment.pk)
    if payment.status == 'paid':
        if payment.provider_id != provider_id:
            raise ValueError('Payment is already completed with a different provider ID.')
        return payment, False

    now = timezone.now()
    payment.status = 'paid'
    payment.provider_id = provider_id
    payment.paid_at = now
    payment.save(update_fields=('status', 'provider_id', 'paid_at', 'updated_at'))

    profile, _ = UserProfile.objects.select_for_update().get_or_create(user=payment.user)
    active_expiry = profile.plan_expires_at
    if profile.plan != 'premium' or not active_expiry or active_expiry <= now:
        active_expiry = now
    profile.plan = 'premium'
    profile.subscription_plan = payment.plan
    profile.plan_expires_at = active_expiry + timedelta(days=max(1, payment.plan.duration_days))
    profile.save(update_fields=('plan', 'subscription_plan', 'plan_expires_at', 'updated_at'))

    Notification.objects.get_or_create(
        recipient=payment.user,
        notification_type='PAYMENT_SUCCESS',
        dedupe_key=f'payment:{payment.pk}',
        defaults={
            'sender': payment.user,
            'message': f'Your {payment.plan.name} plan is active.',
        },
    )
    return payment, True