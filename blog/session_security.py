import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.db.models import F
from django.shortcuts import redirect
from django.utils import timezone

from .models import PendingUserLogin, UserLoginSession, UserProfile


logger = logging.getLogger(__name__)

PENDING_LOGIN_TTL = timedelta(minutes=5)
LOGIN_RESERVATION_TTL = timedelta(minutes=5)
LOGIN_ALLOWANCE_EXHAUSTED_MESSAGE = (
    'Your total successful login allowance has been exhausted.'
)
PENDING_LOGIN_EXPIRED_MESSAGE = (
    'Your pending login has expired. Please verify your credentials again.'
)


@dataclass(frozen=True)
class LoginReservationResult:
    status: str
    pending_login: PendingUserLogin | None = None


def session_tracking_digest(session):
    tracking_id = session.get('_vgh_session_tracking_id')
    if not tracking_id:
        tracking_id = uuid.uuid4().hex
        session['_vgh_session_tracking_id'] = tracking_id
        session.modified = True
    return hashlib.sha256(str(tracking_id).encode('utf-8')).hexdigest()


def _locked_profile(user):
    updated = UserProfile.objects.filter(user=user).update(
        successful_login_count=F('successful_login_count'),
    )
    if not updated:
        UserProfile.objects.get_or_create(user=user)
        UserProfile.objects.filter(user=user).update(
            successful_login_count=F('successful_login_count'),
        )
    return UserProfile.objects.select_for_update().get(user=user)


def _expire_user_sessions(user, now):
    UserLoginSession.objects.filter(
        user=user,
        is_active=True,
        expires_at__lte=now,
    ).update(is_active=False, revoked_at=now)


def _session_counts(user, now):
    sessions = UserLoginSession.objects.filter(
        user=user,
        is_active=True,
        expires_at__gt=now,
    )
    active_count = sessions.filter(
        tracking_id_digest__isnull=False,
    ).count()
    reservation_count = sessions.filter(
        tracking_id_digest__isnull=True,
        reservation_id__isnull=False,
    ).count()
    return active_count, reservation_count


def _create_pending_login(request, user, login_method, now):
    binding = session_tracking_digest(request.session)
    previous_token = request.session.pop('_vgh_pending_login', None)
    if previous_token:
        PendingUserLogin.objects.filter(token=previous_token).delete()
    pending = PendingUserLogin.objects.create(
        token=uuid.uuid4(),
        user=user,
        session_binding_digest=binding,
        login_method=login_method,
        backend_path=getattr(
            user,
            'backend',
            (
                'allauth.account.auth_backends.AuthenticationBackend'
                if login_method == 'Google'
                else 'django.contrib.auth.backends.ModelBackend'
            ),
        ),
        expires_at=now + PENDING_LOGIN_TTL,
    )
    request.session['_vgh_pending_login'] = str(pending.token)
    request.session.modified = True
    return pending


def reserve_login(request, user, login_method):
    session_tracking_digest(request.session)
    now = timezone.now()
    with transaction.atomic():
        profile = _locked_profile(user)
        _expire_user_sessions(user, now)
        active_count, reservation_count = _session_counts(user, now)

        if (
            profile.max_successful_logins is not None
            and profile.successful_login_count + reservation_count
            >= profile.max_successful_logins
        ):
            return LoginReservationResult('allowance')

        if (
            profile.max_active_sessions is not None
            and active_count + reservation_count >= profile.max_active_sessions
        ):
            pending = _create_pending_login(request, user, login_method, now)
            return LoginReservationResult('sessions', pending)

        reservation_id = uuid.uuid4()
        UserLoginSession.objects.create(
            user=user,
            reservation_id=reservation_id,
            expires_at=now + LOGIN_RESERVATION_TTL,
            device_description=device_description(
                request.META.get('HTTP_USER_AGENT', ''),
            ),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:512],
            login_at=now,
            last_activity_at=now,
        )
        request.session['_vgh_login_reservation'] = str(reservation_id)
        request.session['_vgh_login_method'] = login_method
        request.session.modified = True
        return LoginReservationResult('reserved')


def get_pending_login(request):
    token = request.session.get('_vgh_pending_login')
    if not token:
        return None
    now = timezone.now()
    pending = PendingUserLogin.objects.filter(
        token=token,
        session_binding_digest=session_tracking_digest(request.session),
        expires_at__gt=now,
    ).select_related('user').first()
    if pending is None:
        request.session.pop('_vgh_pending_login', None)
        request.session.modified = True
    return pending


def revoke_and_complete_login(request, pending_token, session_id):
    now = timezone.now()
    binding = session_tracking_digest(request.session)
    with transaction.atomic():
        pending = PendingUserLogin.objects.filter(
            token=pending_token,
            session_binding_digest=binding,
            expires_at__gt=now,
        ).select_for_update().select_related('user').first()
        if pending is None:
            return LoginReservationResult('expired')

        profile = _locked_profile(pending.user)
        _expire_user_sessions(pending.user, now)
        active_count, reservation_count = _session_counts(pending.user, now)

        if (
            profile.max_successful_logins is not None
            and profile.successful_login_count + reservation_count
            >= profile.max_successful_logins
        ):
            pending.delete()
            request.session.pop('_vgh_pending_login', None)
            request.session.modified = True
            return LoginReservationResult('allowance')

        selected_session = UserLoginSession.objects.filter(
            pk=session_id,
            user=pending.user,
            is_active=True,
            tracking_id_digest__isnull=False,
            expires_at__gt=now,
        ).select_for_update().first()
        if selected_session is None:
            return LoginReservationResult('invalid_session')

        if profile.max_active_sessions is not None and (
            active_count - 1 + reservation_count >= profile.max_active_sessions
        ):
            return LoginReservationResult('sessions')

        selected_session.is_active = False
        selected_session.revoked_at = now
        selected_session.save(update_fields=('is_active', 'revoked_at'))

        reservation_id = uuid.uuid4()
        UserLoginSession.objects.create(
            user=pending.user,
            reservation_id=reservation_id,
            expires_at=now + LOGIN_RESERVATION_TTL,
            device_description=device_description(
                request.META.get('HTTP_USER_AGENT', ''),
            ),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:512],
            login_at=now,
            last_activity_at=now,
        )
        request.session.pop('_vgh_pending_login', None)
        request.session['_vgh_login_reservation'] = str(reservation_id)
        request.session['_vgh_login_method'] = pending.login_method
        request.session.modified = True
        pending.delete()

        from django.contrib.auth import login

        login(
            request,
            pending.user,
            backend=pending.backend_path,
        )
        request.session.save()
    return LoginReservationResult('completed')


def register_successful_login(sender, request, user, **kwargs):
    if request is None or not hasattr(request, 'session'):
        return

    if not hasattr(request.session, 'session_key'):
        return

    now = timezone.now()
    digest = session_tracking_digest(request.session)
    reservation_token = request.session.pop('_vgh_login_reservation', None)
    request.session.modified = bool(reservation_token) or request.session.modified

    with transaction.atomic():
        profile = _locked_profile(user)
        if reservation_token:
            reservation = UserLoginSession.objects.filter(
                reservation_id=reservation_token,
                user=user,
                is_active=True,
                expires_at__gt=now,
            ).select_for_update().first()
            if reservation is None:
                logger.error(
                    'Login reservation was missing or expired for user %s.',
                    user.pk,
                )
                auth_logout(request)
                request.user = AnonymousUser()
                return
            profile.successful_login_count += 1
            profile.save(update_fields=('successful_login_count', 'updated_at'))
            reservation.tracking_id_digest = digest
            reservation.reservation_id = None
            reservation.last_activity_at = now
            reservation.expires_at = request.session.get_expiry_date()
            reservation.save(update_fields=(
                'tracking_id_digest',
                'reservation_id',
                'last_activity_at',
                'expires_at',
            ))
        else:
            _expire_user_sessions(user, now)
            active_count, reservation_count = _session_counts(user, now)
            if (
                profile.max_successful_logins is not None
                and profile.successful_login_count + reservation_count
                >= profile.max_successful_logins
            ) or (
                profile.max_active_sessions is not None
                and active_count + reservation_count >= profile.max_active_sessions
            ):
                logger.warning(
                    'Rejected an unreserved login for user %s due to account limits.',
                    user.pk,
                )
                auth_logout(request)
                request.user = AnonymousUser()
                return

            profile.successful_login_count += 1
            profile.save(update_fields=('successful_login_count', 'updated_at'))
            UserLoginSession.objects.create(
                user=user,
                tracking_id_digest=digest,
                device_description=device_description(
                    request.META.get('HTTP_USER_AGENT', ''),
                ),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:512],
                login_at=now,
                last_activity_at=now,
                expires_at=request.session.get_expiry_date(),
            )

    request._vgh_session_digest = digest


def remove_logged_out_session(sender, request, user, **kwargs):
    digest = getattr(request, '_vgh_session_digest', '') if request else ''
    if digest:
        UserLoginSession.objects.filter(
            user=user,
            tracking_id_digest=digest,
            is_active=True,
        ).update(is_active=False, revoked_at=timezone.now())


def enforce_active_session(request, user):
    digest = session_tracking_digest(request.session)
    now = timezone.now()
    tracked_session = UserLoginSession.objects.filter(
        user=user,
        tracking_id_digest=digest,
        is_active=True,
        expires_at__gt=now,
    ).first()
    if tracked_session is None:
        auth_logout(request)
        request.user = AnonymousUser()
        return redirect('blog:login')

    request._vgh_session_digest = digest
    tracked_session.last_activity_at = now
    tracked_session.expires_at = request.session.get_expiry_date()
    tracked_session.save(update_fields=('last_activity_at', 'expires_at'))
    return None


def active_session_count(user, now=None):
    return UserLoginSession.objects.filter(
        user=user,
        is_active=True,
        tracking_id_digest__isnull=False,
        expires_at__gt=now or timezone.now(),
    ).count()


def has_active_login_session(user_id, tracking_id):
    if not tracking_id:
        return False
    digest = hashlib.sha256(str(tracking_id).encode('utf-8')).hexdigest()
    return UserLoginSession.objects.filter(
        user_id=user_id,
        tracking_id_digest=digest,
        is_active=True,
        expires_at__gt=timezone.now(),
    ).exists()


def device_description(user_agent):
    agent = user_agent or ''
    lowered = agent.lower()
    if 'edg/' in lowered:
        browser = 'Microsoft Edge'
    elif 'opr/' in lowered or 'opera' in lowered:
        browser = 'Opera'
    elif 'firefox/' in lowered:
        browser = 'Firefox'
    elif 'chrome/' in lowered or 'chromium/' in lowered:
        browser = 'Chrome'
    elif 'safari/' in lowered:
        browser = 'Safari'
    else:
        browser = 'Unknown browser'

    if 'ipad' in lowered:
        device = 'iPad'
    elif 'iphone' in lowered:
        device = 'iPhone'
    elif 'android' in lowered:
        device = 'Android device'
    elif 'windows' in lowered:
        device = 'Windows device'
    elif 'macintosh' in lowered or 'mac os' in lowered:
        device = 'Mac'
    elif 'linux' in lowered:
        device = 'Linux device'
    else:
        device = 'Unknown device'
    return f'{browser} on {device}'


def session_selection_error(status):
    if status == 'expired':
        return PENDING_LOGIN_EXPIRED_MESSAGE
    if status == 'allowance':
        return LOGIN_ALLOWANCE_EXHAUSTED_MESSAGE
    if status == 'invalid_session':
        return 'That active session is no longer available. Refresh and try again.'
    if status == 'sessions':
        return 'The active-session limit is still full. Choose another session to log out.'
    return ''
