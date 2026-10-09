import os
import secrets
import json
import logging
from datetime import timedelta

from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.shortcuts import render, get_object_or_404, redirect
from google import genai
from django.http import (
    HttpResponsePermanentRedirect,
    JsonResponse,
    Http404,
    HttpResponseForbidden,
)
from django.core.exceptions import ImproperlyConfigured

from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import (
    authenticate,
    login,
    logout as auth_logout,
    update_session_auth_hash,
)
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from .models import MessageAttachment
from .services.course_progress import (
    can_access_lesson,
    mark_lesson_completed,
    start_lesson,
)

from .gmail_service import build_site_url, send_gmail
from .forms import (
    CommentForm,
    EmailSignupForm,
    PostForm,
    ProfilePictureForm,
    ProjectForm,
    CommunityPostForm,
    CommunityReplyForm,
)

from .models import (
    Post,
    Lesson,
    Comment,
    UserProfile,
    Enrollment,
    Project,
    ProjectImage,
    ProjectLike,
    ProjectComment,
    ProjectCommentLike,
    ProjectSave,
    ProjectFollow,
    ProjectUpdate,
    ProjectCollaborator,
    ProjectReport,
    ProjectShare,
    ProjectView,
    CommunityPost,
    CommunityReply,
    Conversation,
    Message,
    Assignment,
    AssignmentAudience,
    AssignmentAttempt,
    AssignmentSubmission,
    UserAssignmentProgress,
    PracticeProblem,
    PracticeProblemSet,
    PracticeProgress,
    PracticeSubmission,
    PlaygroundSession,
    MockTest,
    MockTestQuestion,
    MockTestAttempt,
    FollowRequest,
    Notification,
    UserBlock,
    UserLoginSession,
    AITutorConversation,
    AITutorMessage,
)
from .session_security import (
    LOGIN_ALLOWANCE_EXHAUSTED_MESSAGE,
    PENDING_LOGIN_EXPIRED_MESSAGE,
    get_pending_login,
    reserve_login,
    revoke_and_complete_login,
    session_selection_error,
)

from .services.code_execution import (
    CodeExecutionError,
    CodeRunnerUnavailable,
    run_code,
    runner_is_configured,
    supported_languages,
)
from .services.leaderboard import leaderboard_rows

logger = logging.getLogger(__name__)


def _can_view_user_content(profile_user, viewer):
    if viewer.is_authenticated and profile_user == viewer:
        return True

    profile = UserProfile.objects.get_or_create(user=profile_user)[0]
    if profile.is_deactivated or profile.scheduled_deletion_at:
        return False
    if not profile.is_private:
        return True

    return viewer.is_authenticated and FollowRequest.objects.filter(
        sender=viewer,
        receiver=profile_user,
        status='ACCEPTED',
    ).exists()


def _users_blocked(user_a, user_b):
    return UserBlock.objects.filter(
        Q(blocker=user_a, blocked=user_b)
        | Q(blocker=user_b, blocked=user_a)
    ).exists()


def _account_unavailable(user):
    return UserProfile.objects.filter(
        user=user,
    ).filter(
        Q(is_deactivated=True) | Q(scheduled_deletion_at__isnull=False)
    ).exists()


def _get_user_by_username(username):
    user = User.objects.filter(
        username__iexact=username
    ).order_by('pk').first()
    if user is None:
        raise Http404
    return user


def _can_message_between(user_a, user_b):
    if (
        user_a == user_b
        or _users_blocked(user_a, user_b)
        or _account_unavailable(user_a)
        or _account_unavailable(user_b)
    ):
        return False

    return (
        FollowRequest.objects.filter(
            sender=user_a,
            receiver=user_b,
            status='ACCEPTED',
        ).exists()
        and FollowRequest.objects.filter(
            sender=user_b,
            receiver=user_a,
            status='ACCEPTED',
        ).exists()
    )


def _learning_streak_for_user(user):
    activity_days = set(
        PracticeSubmission.objects.filter(user=user).dates(
            'submitted_at',
            'day',
            order='DESC',
        )
    )
    activity_days.update(
        MockTestAttempt.objects.filter(
            user=user,
            status__in=('COMPLETED', 'EXPIRED'),
        ).exclude(
            submitted_at__isnull=True
        ).dates(
            'submitted_at',
            'day',
            order='DESC',
        )
    )
    today = timezone.localdate()
    streak_day = today if today in activity_days else today - timedelta(days=1)
    streak = 0
    while streak_day in activity_days:
        streak += 1
        streak_day -= timedelta(days=1)
    return streak


def _user_content_visibility_filter(owner_field, viewer):
    available_profiles = (
        Q(**{f'{owner_field}__profile_data__is_deactivated': False})
        & Q(**{f'{owner_field}__profile_data__scheduled_deletion_at__isnull': True})
    )
    public_profiles = Q(**{f'{owner_field}__profile_data__is_private': False})
    if viewer.is_authenticated:
        blocked_user_ids = UserBlock.objects.filter(
            blocker=viewer
        ).values_list('blocked_id', flat=True).union(
            UserBlock.objects.filter(
                blocked=viewer
            ).values_list('blocker_id', flat=True)
        )
        visible_followees = FollowRequest.objects.filter(
            sender=viewer,
            status='ACCEPTED',
        ).values_list('receiver_id', flat=True)
        public_profiles = (
            public_profiles
            | Q(**{f'{owner_field}_id__in': visible_followees})
        ) & ~Q(**{f'{owner_field}_id__in': blocked_user_ids})
    return public_profiles & available_profiles


# =========================================================
# COURSE / BLOG LIST uyhnyuyu
# =========================================================

def blog(request):

    search = request.GET.get('search', '').strip()
    category = request.GET.get('category', '').strip()

    posts = Post.objects.filter(
        _user_content_visibility_filter('author', request.user)
    ).order_by('-created_at')

    if search:
        posts = posts.filter(
            title__icontains=search
        )

    if category:
        posts = posts.filter(
            category__iexact=category
        )

    paginator = Paginator(posts, 6)

    page_number = request.GET.get('page')

    posts = paginator.get_page(page_number)

    context = {
        'title': 'Courses',
        'posts': posts,
        'search': search,
        'category': category,
        'categories': Post.objects.exclude(category='').values_list(
            'category', flat=True
        ).distinct().order_by('category'),
    }

    return render(
        request,
        'blog/blog.html',
        context
    )


# =========================================================
# DASHBOARD
# =========================================================

@login_required
def dashboard(request):

    profile, created = UserProfile.objects.get_or_create(
        user=request.user
    )
    if not profile.goal and not profile.onboarding_completed:
        return redirect('blog:choose_goal')

    recent_posts = Post.objects.filter(
        _user_content_visibility_filter('author', request.user)
    ).order_by(
        '-created_at'
    )[:4]

    context = {
        'username': request.user.username,
        'recent_posts': recent_posts,
        'user_profile': profile,
    }

    return render(
        request,
        'blog/dashboard.html',
        context
    )


# =========================================================
# MY LEARNING
# =========================================================

@login_required
def my_learning(request):

    enrollments = Enrollment.objects.filter(
        student=request.user
    ).select_related('course')

    total_courses = enrollments.count()

    completed_courses = enrollments.filter(
        completed=True
    ).count()

    in_progress_courses = enrollments.filter(
        completed=False
    ).count()

    average_progress = enrollments.aggregate(
        average=Avg('progress')
    )['average'] or 0

    context = {
        'enrollments': enrollments,
        'username': request.user.username,
        'total_courses': total_courses,
        'completed_courses': completed_courses,
        'in_progress_courses': in_progress_courses,
        'average_progress': round(average_progress),
    }

    return render(
        request,
        'blog/my_learning.html',
        context
    )


# =========================================================
# CHOOSE GOAL
# =========================================================

@login_required
def choose_goal(request):

    profile, created = UserProfile.objects.get_or_create(
        user=request.user
    )

    if request.method == "POST":

        selected_goal = request.POST.get("goal")

        if selected_goal in dict(UserProfile.GOAL_CHOICES):
            profile.goal = selected_goal
            profile.onboarding_completed = True
            profile.save(update_fields=['goal', 'onboarding_completed', 'updated_at'])

            return redirect("blog:dashboard")

    context = {
        "username": request.user.username,
        "user_profile": profile,
        "goal_options": [
            {
                'value': value,
                'label': label,
                'icon': icon,
                'description': description,
            }
            for (value, label), icon, description in zip(
                UserProfile.GOAL_CHOICES[:8],
                ['🐍', '💻', '🌐', '🧠', '🎤', '🚀', '💼', '✨'],
                [
                    'Build a solid programming foundation with Python.',
                    'Learn the tools to build complete web applications.',
                    'Create powerful web applications with Django.',
                    'Strengthen problem-solving and data structures skills.',
                    'Prepare for technical and behavioral interviews.',
                    'Build real-world applications for your portfolio.',
                    'Develop practical skills for your next career step.',
                    'Set a learning goal that is personal to you.',
                ],
            )
        ],
    }

    return render(
        request,
        "blog/goal.html",
        context
    )


# =========================================================
# COURSE DETAIL
# =========================================================

@login_required
def post_detail(request, slug):

    post = Post.objects.filter(slug=slug).first()
    if post is None and slug.isdecimal():
        return legacy_post_detail(request, int(slug))
    if post is None:
        raise Http404
    if not _can_view_user_content(post.author, request.user):
        return HttpResponseForbidden('This profile content is private.')

    comments = Comment.objects.filter(
        post=post
    ).order_by('-created_at')

    lessons = post.lessons.all()

    enrollment = Enrollment.objects.filter(
        student=request.user,
        course=post
    ).first()

    course_assignments = Assignment.objects.filter(
        Q(assignment_source='COURSE', course=post)
        | Q(assignment_source='COURSE', lesson__course=post),
        status='PUBLISHED',
    ).filter(
        Q(release_date__isnull=True) | Q(release_date__lte=timezone.now())
    ).select_related('course', 'lesson').distinct() if enrollment else Assignment.objects.none()
    assignment_progress = {
        item.assignment_id: item
        for item in UserAssignmentProgress.objects.filter(
            user=request.user,
            assignment__in=course_assignments,
        ).select_related('latest_attempt')
    }
    for assignment in course_assignments:
        assignment.user_progress = assignment_progress.get(assignment.id)

    if request.method == "POST":

        action = request.POST.get("action")

        if action == "enroll":

            Enrollment.objects.get_or_create(
                student=request.user,
                course=post
            )

            return redirect(
                'blog:post_detail',
                slug=post.slug
            )

        if action == "comment":

            form = CommentForm(
                request.POST
            )

            if form.is_valid():

                comment = form.save(
                    commit=False
                )

                comment.post = post
                comment.author = request.user
                comment.save()

                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    profile = UserProfile.objects.get_or_create(user=request.user)[0]
                    return JsonResponse({
                        'success': True,
                        'count': Comment.objects.filter(post=post).count(),
                        'comment': {
                            'id': comment.pk,
                            'username': request.user.username,
                            'profile_url': reverse(
                                'blog:user_profile',
                                kwargs={'username': request.user.username},
                            ),
                            'avatar_url': (
                                profile.profile_picture.url
                                if profile.profile_picture
                                else ''
                            ),
                            'initial': request.user.username[:1].upper(),
                            'content': comment.content,
                            'created_at': timezone.localtime(
                                comment.created_at
                            ).strftime('%d %b %Y, %H:%M'),
                            'edit_url': reverse(
                                'blog:update_comment',
                                args=[comment.pk],
                            ),
                            'delete_url': reverse(
                                'blog:delete_comment',
                                args=[comment.pk],
                            ),
                        },
                    }, status=201)

                return redirect(
                    'blog:post_detail',
                    slug=post.slug
                )
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'Please enter a valid comment.',
                    'field_errors': form.errors.get_json_data(),
                }, status=400)

        else:

            form = CommentForm()

    else:

        form = CommentForm()

    context = {
        'post': post,
        'comments': comments,
        'form': form,
        'lessons': lessons,
        'enrollment': enrollment,
        'course_assignments': course_assignments,
    }

    return render(
        request,
        'blog/post_detail.html',
        context
    )


def legacy_post_detail(request, pk):
    post = get_object_or_404(Post, pk=pk)
    return HttpResponsePermanentRedirect(
        reverse('blog:post_detail', kwargs={'slug': post.slug})
    )


# =========================================================
# LESSON DETAIL
# =========================================================

def _assignment_course(assignment):
    return assignment.course or (assignment.lesson.course if assignment.lesson else None)


def _eligible_assignments(user):
    enrolled_courses = Enrollment.objects.filter(
        student=user
    ).values('course_id')

    standalone = Q(
        assignment_source='STANDALONE',
        audiences__audience_type='ALL_USERS'
    ) | Q(
        assignment_source='STANDALONE',
        audiences__audience_type='SELECTED_USER',
        audiences__user=user
    )
    course = Q(
        assignment_source='COURSE',
        course_id__in=enrolled_courses
    ) | Q(
        assignment_source='COURSE',
        course_id__isnull=True,
        lesson__course_id__in=enrolled_courses
    )
    return Assignment.objects.filter(
        Q(standalone) | Q(course),
        status='PUBLISHED'
    ).filter(
        Q(release_date__isnull=True) | Q(release_date__lte=timezone.now())
    ).distinct().select_related('course', 'lesson', 'lesson__course')


def _can_access_assignment(user, assignment):
    if not assignment or assignment.status != 'PUBLISHED':
        return False
    if assignment.release_date and assignment.release_date > timezone.now():
        return False
    if assignment.assignment_source == 'STANDALONE':
        return assignment.audiences.filter(
            audience_type='ALL_USERS'
        ).exists() or assignment.audiences.filter(
            audience_type='SELECTED_USER', user=user
        ).exists()
    course = _assignment_course(assignment)
    return bool(course and Enrollment.objects.filter(student=user, course=course).exists())


@login_required
def start_lesson_view(request, course_slug, lesson_slug):
    lesson = Lesson.objects.filter(
        slug=lesson_slug,
        course__slug=course_slug,
    ).select_related('course').first()
    if lesson is None and course_slug.isdecimal() and lesson_slug.isdecimal():
        return legacy_start_lesson(
            request,
            int(course_slug),
            int(lesson_slug),
        )
    if lesson is None:
        raise Http404
    if not can_access_lesson(request.user, lesson):
        return HttpResponseForbidden('Enroll in the course and complete earlier lessons first.')

    start_lesson(request.user, lesson)
    return redirect('blog:lesson_detail', slug=lesson.slug)


@login_required
@require_POST
def complete_lesson(request, slug):
    lesson = Lesson.objects.filter(slug=slug).select_related('course').first()
    if lesson is None and slug.isdecimal():
        return legacy_complete_lesson(request, int(slug))
    if lesson is None:
        raise Http404
    if not can_access_lesson(request.user, lesson):
        return HttpResponseForbidden('Enroll in the course and complete earlier lessons first.')

    mark_lesson_completed(request.user, lesson)
    return redirect('blog:lesson_detail', slug=lesson.slug)


def legacy_start_lesson(request, course_pk, lesson_pk):
    lesson = get_object_or_404(Lesson, pk=lesson_pk, course_id=course_pk)
    response = HttpResponsePermanentRedirect(
        reverse(
            'blog:start_lesson',
            kwargs={
                'course_slug': lesson.course.slug,
                'lesson_slug': lesson.slug,
            },
        )
    )
    response.status_code = 308
    return response


def legacy_lesson_detail(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    return HttpResponsePermanentRedirect(
        reverse('blog:lesson_detail', kwargs={'slug': lesson.slug})
    )


def legacy_complete_lesson(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    response = HttpResponsePermanentRedirect(
        reverse('blog:complete_lesson', kwargs={'slug': lesson.slug})
    )
    response.status_code = 308
    return response


def lesson_detail(request, slug):

    lesson = Lesson.objects.filter(slug=slug).select_related('course').first()
    if lesson is None and slug.isdecimal():
        return legacy_lesson_detail(request, int(slug))
    if lesson is None:
        raise Http404

    if not request.user.is_authenticated:
        return redirect('blog:login')

    enrolled = Enrollment.objects.filter(
        student=request.user,
        course=lesson.course
    ).exists()
    assignments = Assignment.objects.filter(
        assignment_source='COURSE',
        status='PUBLISHED',
        lesson=lesson
    ).filter(
        Q(release_date__isnull=True) | Q(release_date__lte=timezone.now())
    ) if enrolled else Assignment.objects.none()

    progress = {
        item.assignment_id: item
        for item in UserAssignmentProgress.objects.filter(
            user=request.user,
            assignment__in=assignments
        )
    }
    for assignment in assignments:
        assignment.user_progress = progress.get(assignment.id)

    context = {
        'lesson': lesson,
        'course': lesson.course,
        'lesson_assignments': assignments,
        'assignment_progress': progress,
        'enrolled': enrolled,
    }

    return render(
        request,
        'blog/lesson_detail.html',
        context
    )


# =========================================================
# CREATE COURSE / POST
# =========================================================

@login_required
def create_post(request):

    if not request.user.is_staff:
        return HttpResponseForbidden()

    if request.method == "POST":

        form = PostForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            post = form.save(
                commit=False
            )

            post.author = request.user
            post.save()

            return redirect(
                'blog:blogpage'
            )

    else:

        form = PostForm()

    context = {
        'form': form
    }

    return render(
        request,
        'blog/create_post.html',
        context
    )


# =========================================================
# UPDATE COURSE / POST
# =========================================================

@login_required
def update_post(request, pk):

    post = get_object_or_404(
        Post,
        pk=pk
    )

    if request.user != post.author:

        return redirect(
            'blog:blogpage'
        )

    if request.method == "POST":

        form = PostForm(
            request.POST,
            request.FILES,
            instance=post
        )

        if form.is_valid():

            form.save()

            return redirect(
                'blog:blogpage'
            )

    else:

        form = PostForm(
            instance=post
        )

    context = {
        'form': form,
    }

    return render(
        request,
        'blog/update_post.html',
        context
    )


# =========================================================
# DELETE COURSE / POST
# =========================================================

@login_required
def delete_post(request, pk):

    post = get_object_or_404(
        Post,
        pk=pk
    )

    if request.user != post.author:

        return redirect(
            'blog:blogpage'
        )

    if request.method == "POST":

        post.delete()

        return redirect(
            'blog:blogpage'
        )

    context = {
        'post': post
    }

    return render(
        request,
        'blog/delete_post.html',
        context
    )


# =========================================================
# SIGN UP
# =========================================================

def signup(request):

    if request.method == "POST":

        form = EmailSignupForm(request.POST, request.FILES)

        if form.is_valid():

            user = form.save()
            login_url = build_site_url(reverse('blog:login'))
            welcome_text = f"""Hello @{user.username},

Welcome to vGrowHub!

Your account has been successfully created.

Username:
@{user.username}

You can now start learning, practicing, building projects, and growing your skills on vGrowHub.

Login to vGrowHub:
{login_url}

If you did not create this account, please contact vGrowHub Support.

Regards,
vGrowHub Team
"""
            welcome_html = f"""
            <html>
              <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #0f172a; background: #f8fafc; padding: 24px;">
                <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 32px;">
                  <h2 style="margin-top: 0; color: #111827;">Welcome to vGrowHub!</h2>
                  <p>Hello @{user.username},</p>
                  <p>Your account has been successfully created.</p>
                  <p><strong>Username:</strong> @{user.username}</p>
                  <p>You can now start learning, practicing, building projects, and growing your skills on vGrowHub.</p>
                  <p><strong>Login to vGrowHub:</strong><br><a href="{login_url}">{login_url}</a></p>
                  <p>If you did not create this account, please contact vGrowHub Support.</p>
                  <p>Regards,<br>vGrowHub Team</p>
                </div>
              </body>
            </html>
            """
            try:
                send_gmail(
                    user.email,
                    "Welcome to vGrowHub — Your account is ready 🎉",
                    welcome_text,
                    welcome_html,
                )
                django_messages.success(
                    request,
                    "Account created successfully! 🎉\nYour vGrowHub account is ready. We’ve sent your welcome email to your registered email address. Please check your Inbox. If you don’t see it within a few minutes, check your Spam or Promotions folder.",
                )
            except Exception:
                logger.exception(
                    "vGrowHub welcome email delivery failed for user %s.",
                    user.pk,
                )
                django_messages.warning(
                    request,
                    "Your account was created successfully, but we couldn't send the welcome email right now. You can continue to log in and try again later.",
                )

            return redirect(
                'blog:login'
            )

    else:

        form = EmailSignupForm()

    return render(
        request,
        'blog/signup.html',
        {'form': form}
    )


# =========================================================
# FORGOT PASSWORD
# =========================================================

def forgot_password(request):

    if request.method == "POST":

        email = request.POST.get(
            "email",
            ""
        ).strip().lower()

        try:

            user = User.objects.get(
                email__iexact=email
            )

            otp = str(
                secrets.randbelow(900000) + 100000
            )

            request.session.pop("reset_email", None)
            request.session.pop("reset_otp", None)
            request.session.pop("otp_verified", None)

            if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
                raise ImproperlyConfigured(
                    "EMAIL_HOST_USER and EMAIL_HOST_PASSWORD must be configured."
                )

            otp_email_body = f"""Hello @{user.username},

We received a request to reset your {settings.SITE_NAME} password.

Your password reset OTP is:

{otp}

This OTP expires according to the existing OTP expiry configuration.

If you did not request this password reset, you can safely ignore this email.

Regards,
{settings.SITE_NAME} Security Team
"""
            otp_email_html = f"""
            <html>
              <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #0f172a; background: #f8fafc; padding: 24px;">
                <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 32px;">
                  <h2 style="margin-top: 0; color: #111827;">vGrowHub Password Reset OTP</h2>
                  <p>Hello @{user.username},</p>
                  <p>We received a request to reset your vGrowHub password.</p>
                  <p><strong>Your password reset OTP is:</strong></p>
                  <p style="font-size: 28px; font-weight: 700; letter-spacing: 0.2em; color: #7c3aed; margin: 18px 0;">{otp}</p>
                  <p>This OTP expires according to the existing OTP expiry configuration.</p>
                  <p>If you did not request this password reset, you can safely ignore this email.</p>
                  <p>Regards,<br>vGrowHub Security Team</p>
                </div>
              </body>
            </html>
            """
            send_gmail(
                user.email,
                "vGrowHub Password Reset OTP",
                otp_email_body,
                otp_email_html,
            )

            request.session["reset_email"] = user.email
            request.session["reset_otp"] = otp
            request.session["otp_verified"] = False

            django_messages.success(
                request,
                "Check your email 📩",
            )
            django_messages.info(
                request,
                "We’ve sent a password reset OTP to your registered email address. Please check your Inbox. If you don’t see it within a few minutes, check your Spam or Promotions folder.",
            )
            django_messages.info(
                request,
                "Enter the OTP here to continue resetting your password.",
            )

            return render(
                request,
                "blog/login.html",
                {
                    "show_forgot": True,
                    "show_otp": True,
                    "reset_email": user.email,
                }
            )

        except User.DoesNotExist:

            return render(
                request,
                "blog/login.html",
                {
                    "show_forgot": True,
                    "error": "No account found with this email."
                }
            )

        except Exception:

            logger.exception("vGrowHub password reset email delivery failed.")

            django_messages.error(
                request,
                "We couldn't send the password reset email right now. Please try again in a few moments.",
            )

            return render(
                request,
                "blog/login.html",
                {
                    "show_forgot": True,
                }
            )

    return render(
        request,
        "blog/login.html",
        {
            "show_forgot": True
        }
    )


# =========================================================
# VERIFY OTP
# =========================================================

def verify_otp(request):

    if request.method == "POST":

        entered_otp = request.POST.get(
            "otp",
            ""
        ).strip()

        saved_otp = request.session.get(
            "reset_otp"
        )

        reset_email = request.session.get(
            "reset_email"
        )

        if not saved_otp or not reset_email:

            return render(
                request,
                "blog/login.html",
                {
                    "show_forgot": True,
                    "show_otp": True,
                    "error": "OTP expired or invalid. Please request a new OTP."
                }
            )

        if entered_otp == saved_otp:

            request.session["otp_verified"] = True

            return render(
                request,
                "blog/login.html",
                {
                    "show_reset": True,
                    "reset_email": reset_email,
                }
            )

        return render(
            request,
            "blog/login.html",
            {
                "show_forgot": True,
                "show_otp": True,
                "reset_email": reset_email,
                "error": "Invalid OTP. Please try again."
            }
        )

    return render(
        request,
        "blog/login.html",
        {
            "show_forgot": True,
            "show_otp": True,
            "reset_email": request.session.get(
                "reset_email"
            ),
        }
    )


# =========================================================
# RESET PASSWORD
# =========================================================

def reset_password(request):

    if not request.session.get(
        "otp_verified"
    ):

        return redirect(
            "blog:login"
        )

    if request.method == "POST":

        password1 = request.POST.get(
            "password1",
            ""
        )

        password2 = request.POST.get(
            "password2",
            ""
        )

        if password1 != password2:

            return render(
                request,
                "blog/login.html",
                {
                    "show_reset": True,
                    "reset_email": request.session.get(
                        "reset_email"
                    ),
                    "error": "Passwords do not match."
                }
            )

        if len(password1) < 8:

            return render(
                request,
                "blog/login.html",
                {
                    "show_reset": True,
                    "reset_email": request.session.get(
                        "reset_email"
                    ),
                    "error": "Password must be at least 8 characters."
                }
            )

        email = request.session.get(
            "reset_email"
        )

        try:

            user = User.objects.get(
                email__iexact=email
            )

            user.set_password(
                password1
            )

            user.save()

            request.session.pop(
                "reset_email",
                None
            )

            request.session.pop(
                "reset_otp",
                None
            )

            request.session.pop(
                "otp_verified",
                None
            )

            return render(
                request,
                "blog/login.html",
                {
                    "password_changed": True
                }
            )

        except User.DoesNotExist:

            return render(
                request,
                "blog/login.html",
                {
                    "show_reset": True,
                    "error": "Account not found."
                }
            )

    return render(
        request,
        "blog/login.html",
        {
            "show_reset": True,
            "reset_email": request.session.get(
                "reset_email"
            ),
        }
    )


# =========================================================
# EMAIL LOGIN
# =========================================================

def login_view(request):

    if request.user.is_authenticated:
        return redirect("blog:dashboard")

    login_error = request.session.pop('_vgh_login_error', None)

    if request.method == "POST":

        identifier = request.POST.get(
            "username",
            ""
        ).strip()

        password = request.POST.get(
            "password",
            ""
        )

        users = User.objects.filter(
            Q(username__iexact=identifier) |
            Q(email__iexact=identifier)
        )

        authenticated_user = None
        for user in users:
            authenticated_user = authenticate(
                request,
                username=user.username,
                password=password
            )

            if authenticated_user is not None:
                break

        if authenticated_user is not None:
            reservation = reserve_login(request, authenticated_user, 'Password')
            if reservation.status == 'sessions':
                return redirect('blog:manage_active_sessions')
            if reservation.status == 'allowance':
                return render(
                    request,
                    "blog/login.html",
                    {"error": LOGIN_ALLOWANCE_EXHAUSTED_MESSAGE},
                )
            login(
                request,
                authenticated_user
            )

            return redirect(
                "blog:dashboard"
            )

        return render(
            request,
            "blog/login.html",
            {
                "error": "Invalid username/email or password.",
            }
        )

    return render(request, "blog/login.html", {"error": login_error})


@require_GET
def manage_active_sessions(request):
    if request.user.is_authenticated:
        return redirect('blog:dashboard')

    pending = get_pending_login(request)
    if pending is None:
        request.session['_vgh_login_error'] = PENDING_LOGIN_EXPIRED_MESSAGE
        request.session.modified = True
        return redirect('blog:login')

    sessions = UserLoginSession.objects.filter(
        user=pending.user,
        is_active=True,
        tracking_id_digest__isnull=False,
        expires_at__gt=timezone.now(),
    ).only(
        'id',
        'device_description',
        'login_at',
        'last_activity_at',
    )
    return render(
        request,
        'blog/manage_active_sessions.html',
        {
            'sessions': sessions,
            'error': request.GET.get('error', ''),
        },
    )


@require_POST
def cancel_pending_login(request):
    pending = get_pending_login(request)
    if pending is not None:
        pending.delete()
    request.session.pop('_vgh_pending_login', None)
    request.session.modified = True
    return redirect('blog:login')


@require_POST
def replace_active_session(request):
    pending = get_pending_login(request)
    if pending is None:
        request.session['_vgh_login_error'] = PENDING_LOGIN_EXPIRED_MESSAGE
        request.session.modified = True
        return redirect('blog:login')

    session_id = request.POST.get('active_session_id')
    if not session_id or not session_id.isdecimal():
        return redirect('blog:manage_active_sessions')

    result = revoke_and_complete_login(
        request,
        pending.token,
        int(session_id),
    )
    if result.status == 'completed':
        return redirect('blog:dashboard')
    if result.status in ('expired', 'allowance'):
        request.session['_vgh_login_error'] = session_selection_error(result.status)
        request.session.modified = True
        return redirect('blog:login')
    return redirect(
        f"{reverse('blog:manage_active_sessions')}?error="
        f"{session_selection_error(result.status)}"
    )


@require_GET
def global_search(request):
    query = (request.GET.get('q') or request.GET.get('search') or '').strip()
    if not query:
        return JsonResponse({
            'navigation': [],
            'content': [],
        })

    normalized_query = query.casefold()

    def score_result(label, description=''):
        label_text = (label or '').casefold()
        description_text = (description or '').casefold()
        if not label_text:
            return 0
        if label_text == normalized_query:
            return 150
        if label_text.startswith(normalized_query):
            return 120
        if normalized_query in label_text:
            return 90
        if description_text.startswith(normalized_query):
            return 75
        if normalized_query in description_text:
            return 60
        return 0

    navigation = []
    nav_items = [
        {'label': 'Dashboard', 'url': reverse('blog:dashboard'), 'description': 'Overview and learning progress', 'category': 'Navigation', 'icon': 'grid'},
        {'label': 'Courses', 'url': reverse('blog:blogpage'), 'description': 'Explore courses and lessons', 'category': 'Navigation', 'icon': 'book'},
        {'label': 'My Learning', 'url': reverse('blog:my_learning'), 'description': 'Your learning dashboard', 'category': 'Navigation', 'icon': 'mortarboard'},
        {'label': 'Practice', 'url': reverse('blog:practice'), 'description': 'Coding challenges and practice', 'category': 'Navigation', 'icon': 'lightning-charge'},
        {'label': 'Assignments', 'url': reverse('blog:assignments'), 'description': 'Course tasks and submissions', 'category': 'Navigation', 'icon': 'clipboard-check'},
        {'label': 'AI Tutor', 'url': reverse('blog:ai_tutor'), 'description': 'Ask for help and ideas', 'category': 'Navigation', 'icon': 'robot'},
        {'label': 'Projects', 'url': reverse('blog:projects'), 'description': 'Build and share projects', 'category': 'Navigation', 'icon': 'folder2-open'},
        {'label': 'Community', 'url': reverse('blog:community'), 'description': 'Connect with fellow learners', 'category': 'Navigation', 'icon': 'people'},
        {'label': 'Messages', 'url': reverse('blog:messages'), 'description': 'Chat and direct conversations', 'category': 'Navigation', 'icon': 'chat-dots'},
        {'label': 'Notifications', 'url': reverse('blog:notifications'), 'description': 'Updates and alerts', 'category': 'Navigation', 'icon': 'bell'},
        {'label': 'Profile', 'url': reverse('blog:profile'), 'description': 'View and manage your profile', 'category': 'Navigation', 'icon': 'person-circle'},
        {'label': 'Settings', 'url': reverse('blog:settings'), 'description': 'Manage account preferences', 'category': 'Navigation', 'icon': 'gear'},
    ]

    if not request.user.is_authenticated:
        nav_items = [
            {'label': 'Courses', 'url': reverse('blog:blogpage'), 'description': 'Explore available courses', 'category': 'Navigation', 'icon': 'book'},
            {'label': 'Sign in', 'url': reverse('blog:login'), 'description': 'Access your learning dashboard', 'category': 'Navigation', 'icon': 'box-arrow-in-right'},
            {'label': 'Create account', 'url': reverse('blog:signup'), 'description': 'Join vGrowHub', 'category': 'Navigation', 'icon': 'person-plus'},
        ]

    for item in nav_items:
        item_score = score_result(item['label'], item.get('description', ''))
        if item_score:
            navigation.append({
                **item,
                'score': item_score,
            })

    content = []
    content_items = []

    accessible_posts = Post.objects.filter(
        _user_content_visibility_filter('author', request.user)
    ).select_related('author').order_by('-created_at')[:12]
    for post in accessible_posts:
        score = score_result(post.title, post.category)
        if score:
            content_items.append({
                'label': post.title,
                'url': reverse('blog:post_detail', kwargs={'slug': post.slug}),
                'description': post.category,
                'category': 'Courses',
                'icon': 'book',
                'score': score,
            })

    practice_problems = PracticeProblem.objects.filter(active=True).order_by('title')[:12]
    for problem in practice_problems:
        score = score_result(problem.title, problem.category)
        if score:
            content_items.append({
                'label': problem.title,
                'url': reverse('blog:practice_problem_detail', kwargs={'slug': problem.slug}),
                'description': f"{problem.category.title()} practice problem",
                'category': 'Practice',
                'icon': 'lightning-charge',
                'score': score,
            })

    projects = Project.objects.select_related('owner').order_by('-created_at')[:12]
    for project in projects:
        score = score_result(project.title, project.description or '')
        if score:
            content_items.append({
                'label': project.title,
                'url': reverse('blog:project_detail', kwargs={'pk': project.pk}),
                'description': project.description[:120] if project.description else 'Project',
                'category': 'Community',
                'icon': 'folder2-open',
                'score': score,
            })

    content = sorted(content_items, key=lambda item: (-item['score'], item['label']))[:8]
    navigation = sorted(navigation, key=lambda item: (-item['score'], item['label']))[:8]

    return JsonResponse({
        'navigation': navigation,
        'content': content,
    })


# =========================================================
# DELETE COMMENT
# =========================================================

@login_required
def delete_comment(request, pk):

    comment = get_object_or_404(
        Comment,
        pk=pk
    )

    if request.user != comment.author:

        return redirect(
            'blog:blogpage'
        )

    if request.method == "POST":

        post_slug = comment.post.slug

        comment.delete()

        return redirect(
            'blog:post_detail',
            slug=post_slug
        )

    context = {
        'comment': comment
    }

    return render(
        request,
        'blog/delete_comment.html',
        context
    )


# =========================================================
# UPDATE COMMENT
# =========================================================

@login_required
def update_comment(request, pk):

    comment = get_object_or_404(
        Comment,
        pk=pk
    )

    if request.user != comment.author:

        return redirect(
            'blog:blogpage'
        )

    if request.method == "POST":

        form = CommentForm(
            request.POST,
            instance=comment
        )

        if form.is_valid():

            form.save()

            return redirect(
                'blog:post_detail',
                slug=comment.post.slug
            )

    else:

        form = CommentForm(
            instance=comment
        )

    context = {
        'form': form
    }

    return render(
        request,
        'blog/update_comment.html',
        context
    )


# =========================================================
# PROFILE
# =========================================================

@login_required
def profile(request):
    profile_picture_form = ProfilePictureForm()

    profile, created = UserProfile.objects.get_or_create(
        user=request.user
    )

    if request.method == "POST":
        profile_picture_form = ProfilePictureForm(
            request.POST,
            request.FILES,
        )
        remove_picture = request.POST.get('remove_picture') == '1'
        if profile_picture_form.is_valid():
            new_picture = profile_picture_form.cleaned_data.get('profile_picture')
            if remove_picture and new_picture:
                profile_picture_form.add_error(
                    None,
                    'Choose a new photo or remove the current photo, not both.',
                )
            elif remove_picture:
                old_picture = profile.profile_picture
                old_name = old_picture.name if old_picture else None
                old_storage = old_picture.storage if old_picture else None
                profile.profile_picture = None
                profile.save(update_fields=['profile_picture', 'updated_at'])
                if old_name:
                    try:
                        old_storage.delete(old_name)
                    except Exception as error:
                        logger.error(
                            "Old profile picture cleanup failed (%s).",
                            type(error).__name__,
                        )
                return redirect('blog:profile')
            elif new_picture:
                old_picture = profile.profile_picture
                old_name = old_picture.name if old_picture else None
                old_storage = old_picture.storage if old_picture else None
                profile.profile_picture.save(
                    new_picture.name,
                    new_picture,
                    save=False,
                )
                profile.save(update_fields=['profile_picture', 'updated_at'])
                if old_name and old_name != profile.profile_picture.name:
                    try:
                        old_storage.delete(old_name)
                    except Exception as error:
                        logger.error(
                            "Old profile picture cleanup failed (%s).",
                            type(error).__name__,
                        )
                return redirect('blog:profile')
            else:
                profile_picture_form.add_error(
                    None,
                    'Choose a photo or select Remove photo.',
                )

    active_tab = request.GET.get('tab', 'community').lower()
    if active_tab not in {'community', 'projects'}:
        active_tab = 'community'

    posts = Post.objects.filter(
        author=request.user
    ).order_by('-created_at')

    projects = Project.objects.filter(
        owner=request.user
    ).order_by('-created_at')

    context = {
        'posts': posts,
        'projects': projects,
        'community_posts': posts,
        'project_contributions': projects,
        'community_count': posts.count(),
        'project_count': projects.count(),
        'active_tab': active_tab,
        'username': request.user.username,
        'user_profile': profile,
        'display_name': (
            profile.display_name
            or request.user.get_full_name()
            or request.user.username
        ),
        'profile_picture_form': profile_picture_form,
    }

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(
            request,
            'blog/includes/profile_contributions.html',
            context,
        )

    return render(
        request,
        'blog/profile.html',
        context
    )

# =========================================================
# USER PROFILE
# =========================================================

@require_GET
def user_profile(request, username):

    profile_user = User.objects.filter(
        username__iexact=username
    ).order_by('pk').first()
    if profile_user is None:
        if username.isdecimal():
            return legacy_user_profile(request, int(username))
        raise Http404
    is_owner = request.user.is_authenticated and request.user == profile_user
    blocked_by_viewer = (
        request.user.is_authenticated
        and not is_owner
        and UserBlock.objects.filter(
            blocker=request.user,
            blocked=profile_user,
        ).exists()
    )
    if (
        request.user.is_authenticated
        and not is_owner
        and UserBlock.objects.filter(
            blocker=profile_user,
            blocked=request.user,
        ).exists()
    ):
        raise Http404

    user_profile, created = UserProfile.objects.get_or_create(
        user=profile_user
    )
    if user_profile.is_deactivated or user_profile.scheduled_deletion_at:
        raise Http404

    follower_count = FollowRequest.objects.filter(
        receiver=profile_user,
        status="ACCEPTED"
    ).count()

    following_count = FollowRequest.objects.filter(
        sender=profile_user,
        status="ACCEPTED"
    ).count()

    is_following = False
    follows_viewer = False
    outgoing_pending = False
    incoming_request = None
    if request.user.is_authenticated and not is_owner:
        is_following = FollowRequest.objects.filter(
            sender=request.user,
            receiver=profile_user,
            status="ACCEPTED"
        ).exists()
        outgoing_pending = FollowRequest.objects.filter(
            sender=request.user,
            receiver=profile_user,
            status="PENDING"
        ).exists()
        follows_viewer = FollowRequest.objects.filter(
            sender=profile_user,
            receiver=request.user,
            status="ACCEPTED"
        ).exists()
        incoming_request = FollowRequest.objects.filter(
            sender=profile_user,
            receiver=request.user,
            status="PENDING"
        ).first()

    can_view_content = not blocked_by_viewer and (
        is_owner
        or not user_profile.is_private
        or is_following
    )
    posts = Post.objects.filter(
        author=profile_user
    ).order_by("-created_at") if can_view_content else Post.objects.none()
    projects = Project.objects.filter(
        owner=profile_user
    ).order_by("-created_at") if can_view_content else Project.objects.none()


    context = {
        "profile_user": profile_user,
        "user_profile": user_profile,
        "display_name": (
            user_profile.display_name
            or profile_user.get_full_name()
            or profile_user.username
        ),
        "posts": posts,
        "projects": projects,
        "is_private": user_profile.is_private,
        "can_view_content": can_view_content,
        "is_following": is_following,
        "follows_viewer": follows_viewer,
        "can_message": (
            request.user.is_authenticated
            and _can_message_between(request.user, profile_user)
        ),
        "outgoing_pending": outgoing_pending,
        "incoming_request_id": incoming_request.id if incoming_request else None,
        "incoming_pending": incoming_request is not None,
        "follower_count": follower_count,
        "following_count": following_count,
        "post_count": posts.count(),
        "project_count": projects.count(),
        "profile_like_count": 0,
        "learning_streak": _learning_streak_for_user(profile_user),
        "is_owner": is_owner,
        "blocked_by_viewer": blocked_by_viewer,
    }

    return render(
        request,
        "blog/user_profile.html",
        context
    )


def legacy_user_profile(request, user_id):
    profile_user = get_object_or_404(User, pk=user_id)
    return HttpResponsePermanentRedirect(
        reverse(
            'blog:user_profile',
            kwargs={'username': profile_user.username},
        )
    )


@login_required
def followers_list(request, username):
    profile_user = _get_user_by_username(username)
    if _account_unavailable(profile_user):
        raise Http404
    if _users_blocked(request.user, profile_user):
        raise Http404
    blocked_user_ids = UserBlock.objects.filter(
        blocker=request.user
    ).values_list('blocked_id', flat=True).union(
        UserBlock.objects.filter(
            blocked=request.user
        ).values_list('blocker_id', flat=True)
    )

    followers = FollowRequest.objects.filter(
        receiver=profile_user,
        status="ACCEPTED"
    ).exclude(
        sender__profile_data__is_deactivated=True
    ).filter(
        sender__profile_data__scheduled_deletion_at__isnull=True
    ).exclude(
        sender_id__in=blocked_user_ids
    ).select_related("sender", "sender__profile_data")

    return render(
        request,
        "blog/followers.html",
        {
            "profile_user": profile_user,
            "followers": followers,
        }
    )


@login_required
def following_list(request, username):
    profile_user = _get_user_by_username(username)
    if _account_unavailable(profile_user):
        raise Http404
    if _users_blocked(request.user, profile_user):
        raise Http404
    blocked_user_ids = UserBlock.objects.filter(
        blocker=request.user
    ).values_list('blocked_id', flat=True).union(
        UserBlock.objects.filter(
            blocked=request.user
        ).values_list('blocker_id', flat=True)
    )

    following = FollowRequest.objects.filter(
        sender=profile_user,
        status="ACCEPTED"
    ).exclude(
        receiver__profile_data__is_deactivated=True
    ).filter(
        receiver__profile_data__scheduled_deletion_at__isnull=True
    ).exclude(
        receiver_id__in=blocked_user_ids
    ).select_related("receiver", "receiver__profile_data")

    return render(
        request,
        "blog/following.html",
        {
            "profile_user": profile_user,
            "following": following,
        }
    )
    
# =========================================================
# PERSONAL CHAT CONNECT
# =========================================================


@login_required
def send_follow_request(request, username):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)

    receiver = _get_user_by_username(username)
    if request.user == receiver:
        return JsonResponse({'success': False, 'error': 'You cannot follow yourself.'}, status=400)
    if _account_unavailable(receiver):
        return JsonResponse({'success': False, 'error': 'This account is unavailable.'}, status=404)
    if _users_blocked(request.user, receiver):
        return JsonResponse({'success': False, 'error': 'This action is unavailable.'}, status=403)

    with transaction.atomic():
        follow_request = FollowRequest.objects.select_for_update().filter(
            sender=request.user,
            receiver=receiver,
        ).first()
        if follow_request and follow_request.status == 'PENDING':
            return JsonResponse({
                'success': False,
                'status': 'PENDING',
                'error': 'Follow request already pending.',
            }, status=409)
        if follow_request and follow_request.status == 'ACCEPTED':
            return JsonResponse({
                'success': False,
                'status': 'ACCEPTED',
                'error': 'You are already following this user.',
            }, status=409)

        if follow_request:
            follow_request.status = 'PENDING'
            follow_request.save(update_fields=['status', 'updated_at'])
        else:
            follow_request = FollowRequest.objects.create(
                sender=request.user,
                receiver=receiver,
                status='PENDING',
            )

        sender_profile = UserProfile.objects.get_or_create(user=request.user)[0]
        sender_name = (
            sender_profile.display_name
            or request.user.get_full_name()
            or request.user.username
        )
        Notification.objects.create(
            recipient=receiver,
            sender=request.user,
            notification_type='FOLLOW_REQUEST',
            message=f'{sender_name} (@{request.user.username}) sent you a follow request.',
        )

    return JsonResponse({
        'success': True,
        'status': 'PENDING',
        'request_id': follow_request.id,
        'message': 'Follow request sent.',
    })


@login_required
def cancel_follow_request(request, username):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)
    receiver = _get_user_by_username(username)
    if _users_blocked(request.user, receiver):
        return JsonResponse({'success': False, 'error': 'This action is unavailable.'}, status=403)
    with transaction.atomic():
        follow_request = FollowRequest.objects.select_for_update().filter(
            sender=request.user,
            receiver=receiver,
        ).first()
        if not follow_request or follow_request.status != 'PENDING':
            message = 'That follow request has already been processed.'
            if request.headers.get('x-requested-with') != 'XMLHttpRequest':
                return redirect('blog:user_profile', username=receiver.username)
            return JsonResponse({
                'success': False,
                'status': follow_request.status if follow_request else 'NONE',
                'error': message,
            }, status=409)
        follow_request.delete()
        Notification.objects.filter(
            recipient=receiver,
            sender=request.user,
            notification_type='FOLLOW_REQUEST',
            is_read=False,
        ).update(is_read=True)
    return JsonResponse({'success': True, 'status': 'NONE', 'message': 'Follow request cancelled.'})


@login_required
def accept_follow_request(request, request_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)
    with transaction.atomic():
        follow_request = FollowRequest.objects.select_for_update().filter(
            id=request_id,
            receiver=request.user,
        ).select_related('sender').first()
        if not follow_request or follow_request.status != 'PENDING':
            message = 'That follow request has already been processed.'
            if request.headers.get('x-requested-with') != 'XMLHttpRequest':
                return redirect('blog:notifications')
            return JsonResponse({
                'success': False,
                'status': follow_request.status if follow_request else 'NONE',
                'error': message,
            }, status=409)
        if _users_blocked(request.user, follow_request.sender):
            return JsonResponse({'success': False, 'error': 'This action is unavailable.'}, status=403)

        follow_request.status = 'ACCEPTED'
        follow_request.save(update_fields=['status', 'updated_at'])
        Notification.objects.filter(
            recipient=request.user,
            sender=follow_request.sender,
            notification_type__in=['FOLLOW_REQUEST', 'FOLLOW_BACK'],
        ).update(is_read=True)
        receiver_profile = UserProfile.objects.get_or_create(user=request.user)[0]
        receiver_name = (
            receiver_profile.display_name
            or request.user.get_full_name()
            or request.user.username
        )
        Notification.objects.create(
            recipient=follow_request.sender,
            sender=request.user,
            notification_type='FOLLOW_ACCEPTED',
            message=f'{receiver_name} (@{request.user.username}) accepted your follow request.',
        )

    if _can_message_between(request.user, follow_request.sender):
        conversation = Conversation.objects.filter(project__isnull=True).filter(
            Q(project_owner=request.user, participant=follow_request.sender)
            | Q(project_owner=follow_request.sender, participant=request.user)
        ).first()
        if conversation is None:
            conversation = Conversation.objects.create(
                project=None,
                project_owner=request.user,
                participant=follow_request.sender,
            )
        redirect_url = reverse(
            'blog:conversation_detail',
            args=[conversation.id],
        )
    else:
        redirect_url = reverse(
            'blog:user_profile',
            kwargs={'username': follow_request.sender.username},
        )
    if request.headers.get('x-requested-with') != 'XMLHttpRequest':
        return redirect('blog:notifications')
    return JsonResponse({
        'success': True,
        'status': 'ACCEPTED',
        'redirect_url': redirect_url,
        'message': 'Follow request accepted.',
    })


@login_required
def reject_follow_request(request, request_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)
    with transaction.atomic():
        follow_request = FollowRequest.objects.select_for_update().filter(
            id=request_id,
            receiver=request.user,
        ).select_related('sender').first()
        if not follow_request or follow_request.status != 'PENDING':
            message = 'That follow request has already been processed.'
            if request.headers.get('x-requested-with') != 'XMLHttpRequest':
                return redirect('blog:notifications')
            return JsonResponse({
                'success': False,
                'status': follow_request.status if follow_request else 'NONE',
                'error': message,
            }, status=409)
        if _users_blocked(request.user, follow_request.sender):
            return JsonResponse({'success': False, 'error': 'This action is unavailable.'}, status=403)

        follow_request.status = 'REJECTED'
        follow_request.save(update_fields=['status', 'updated_at'])
        Notification.objects.filter(
            recipient=request.user,
            sender=follow_request.sender,
            notification_type__in=['FOLLOW_REQUEST', 'FOLLOW_BACK'],
        ).update(is_read=True)
    if request.headers.get('x-requested-with') != 'XMLHttpRequest':
        return redirect('blog:notifications')
    return JsonResponse({'success': True, 'status': 'REJECTED', 'message': 'Follow request rejected.'})


@login_required
def unfollow_user(request, username):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)
    target_user = _get_user_by_username(username)
    if request.user == target_user:
        return JsonResponse({'success': False, 'error': 'You cannot unfollow yourself.'}, status=400)
    if _users_blocked(request.user, target_user):
        return JsonResponse({'success': False, 'error': 'This action is unavailable.'}, status=403)
    follow_request = FollowRequest.objects.filter(
        sender=request.user,
        receiver=target_user,
        status='ACCEPTED',
    ).first()
    if not follow_request:
        return JsonResponse({'success': False, 'error': 'You are not following this user.'}, status=400)
    follow_request.delete()
    return JsonResponse({'success': True, 'status': 'NONE', 'message': 'User unfollowed.'})


@login_required
def start_personal_chat(request, username):

    if request.method != "POST":

        return JsonResponse({
            "success": False,
            "error": "Invalid request."
        }, status=400)

    profile_user = get_object_or_404(
        User,
        username__iexact=username
    )

    if request.user == profile_user:

        return JsonResponse({
            "success": False,
            "error": "You cannot connect with yourself."
        }, status=400)
    if not _can_message_between(request.user, profile_user):
        return JsonResponse({
            'success': False,
            'error': 'You can message only people who follow you back.',
        }, status=403)

    conversation = Conversation.objects.filter(
        project__isnull=True
    ).filter(
        Q(
            project_owner=request.user,
            participant=profile_user
        ) |
        Q(
            project_owner=profile_user,
            participant=request.user
        )
    ).first()

    if conversation is None:

        conversation = Conversation.objects.create(
            project=None,
            project_owner=request.user,
            participant=profile_user
        )

    return JsonResponse({
        "success": True,
        "conversation_id": conversation.id,
        "redirect_url": reverse(
            "blog:conversation_detail",
            args=[conversation.id]
        ),
        
        "message": "Conversation ready."
    })


@login_required
def block_user(request, username):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)
    target = _get_user_by_username(username)
    if target == request.user:
        return JsonResponse({'success': False, 'error': 'You cannot block yourself.'}, status=400)

    UserBlock.objects.get_or_create(blocker=request.user, blocked=target)
    FollowRequest.objects.filter(
        Q(sender=request.user, receiver=target)
        | Q(sender=target, receiver=request.user)
    ).delete()
    Notification.objects.filter(
        Q(recipient=request.user, sender=target)
        | Q(recipient=target, sender=request.user),
        notification_type__in=['FOLLOW_REQUEST', 'FOLLOW_BACK'],
    ).delete()
    return redirect('blog:user_profile', username=target.username)


@login_required
def unblock_user(request, username):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)
    target = _get_user_by_username(username)
    UserBlock.objects.filter(blocker=request.user, blocked=target).delete()
    return redirect('blog:user_profile', username=target.username)


@login_required
def settings_view(request):

    profile = UserProfile.objects.get_or_create(user=request.user)[0]
    if request.method == 'POST':
        profile.is_private = request.POST.get('is_private') == 'on'
        profile.save(update_fields=['is_private', 'updated_at'])
        return redirect('blog:settings')

    return render(
        request,
        'blog/settings.html',
        {
            'user_profile': profile,
            'goal_display': profile.get_goal_display() if profile.goal else 'Not selected',
            'has_usable_password': request.user.has_usable_password(),
        }
    )


@login_required
def change_password(request):
    if not request.user.has_usable_password():
        return render(
            request,
            'blog/password_change.html',
            {'password_unavailable': True},
        )

    form = PasswordChangeForm(
        user=request.user,
        data=request.POST if request.method == 'POST' else None,
    )
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        django_messages.success(request, 'Your password was changed successfully.')
        return redirect('blog:settings')

    return render(
        request,
        'blog/password_change.html',
        {'form': form},
    )


def _account_action_confirmed(request):
    if request.user.has_usable_password():
        return request.user.check_password(request.POST.get('password', ''))
    expected_email = (request.user.email or '').strip().casefold()
    submitted_email = request.POST.get('email', '').strip().casefold()
    return bool(expected_email and submitted_email == expected_email)


@login_required
@require_POST
def deactivate_account(request):
    if request.POST.get('confirmation') != 'DEACTIVATE' or not _account_action_confirmed(request):
        django_messages.error(
            request,
            'Confirm with your password (or account email) and type DEACTIVATE.',
        )
        return redirect('blog:settings')

    profile = UserProfile.objects.get_or_create(user=request.user)[0]
    now = timezone.now()
    profile.is_deactivated = True
    profile.deactivated_at = now
    profile.deletion_requested_at = None
    profile.scheduled_deletion_at = None
    profile.save(update_fields=[
        'is_deactivated',
        'deactivated_at',
        'deletion_requested_at',
        'scheduled_deletion_at',
        'updated_at',
    ])
    auth_logout(request)
    return redirect('blog:account_recovery')


@login_required
@require_POST
def request_account_deletion(request):
    if request.POST.get('confirmation') != 'DELETE' or not _account_action_confirmed(request):
        django_messages.error(
            request,
            'Confirm with your password (or account email) and type DELETE.',
        )
        return redirect('blog:settings')

    profile = UserProfile.objects.get_or_create(user=request.user)[0]
    now = timezone.now()
    profile.is_deactivated = True
    profile.deactivated_at = now
    profile.deletion_requested_at = now
    profile.scheduled_deletion_at = now + timedelta(days=30)
    profile.save(update_fields=[
        'is_deactivated',
        'deactivated_at',
        'deletion_requested_at',
        'scheduled_deletion_at',
        'updated_at',
    ])
    auth_logout(request)
    return redirect('blog:account_recovery')


def account_recovery(request):
    if not request.user.is_authenticated:
        return render(
            request,
            'blog/account_recovery.html',
            {'needs_login': True},
        )

    profile = UserProfile.objects.get_or_create(user=request.user)[0]
    if not profile.is_deactivated and not profile.scheduled_deletion_at:
        return redirect('blog:dashboard')

    error = None
    if request.method == 'POST':
        if request.POST.get('action') not in {'reactivate', 'cancel_deletion'}:
            error = 'Choose a valid account recovery action.'
        elif not _account_action_confirmed(request):
            error = 'Your password or account email did not match.'
        else:
            now = timezone.now()
            restore_until = profile.scheduled_deletion_at
            if restore_until is None and profile.deactivated_at:
                restore_until = profile.deactivated_at + timedelta(days=30)
            if restore_until is None or now > restore_until:
                error = 'The 30-day account recovery period has expired.'
            else:
                profile.is_deactivated = False
                profile.deactivated_at = None
                profile.deletion_requested_at = None
                profile.scheduled_deletion_at = None
                profile.save(update_fields=[
                    'is_deactivated',
                    'deactivated_at',
                    'deletion_requested_at',
                    'scheduled_deletion_at',
                    'updated_at',
                ])
                django_messages.success(request, 'Your account is active again.')
                return redirect('blog:settings')

    return render(
        request,
        'blog/account_recovery.html',
        {
            'needs_login': False,
            'user_profile': profile,
            'error': error,
            'has_usable_password': request.user.has_usable_password(),
        },
    )


# =========================================================
# NOTIFICATIONS
# =========================================================

@login_required
def notifications(request):
    if request.method == 'POST':
        notification_id = request.POST.get('notification_id')
        if notification_id:
            Notification.objects.filter(
                id=notification_id,
                recipient=request.user,
            ).update(is_read=True)
        else:
            Notification.objects.filter(
                recipient=request.user,
                is_read=False,
            ).update(is_read=True)
        return redirect('blog:notifications')

    blocked_user_ids = UserBlock.objects.filter(
        blocker=request.user
    ).values_list('blocked_id', flat=True).union(
        UserBlock.objects.filter(
            blocked=request.user
        ).values_list('blocker_id', flat=True)
    )
    notifications_list = list(
        Notification.objects.filter(
            recipient=request.user,
        ).exclude(
            sender_id__in=blocked_user_ids,
        ).select_related(
            'sender',
            'sender__profile_data',
            'community_post',
        )
    )
    pending_requests = {}
    for follow_request in FollowRequest.objects.filter(
        receiver=request.user,
        status='PENDING',
    ).order_by('created_at'):
        pending_requests[follow_request.sender_id] = follow_request
    for notification in notifications_list:
        if notification.notification_type in {'FOLLOW_REQUEST', 'FOLLOW_BACK'}:
            pending_request = pending_requests.get(notification.sender_id)
            notification.pending_follow_request = pending_requests.get(
                notification.sender_id
            ) if (
                pending_request
                and notification.created_at >= pending_request.created_at
            ) else None

    return render(request, 'blog/notifications.html', {
        'notifications': notifications_list,
    })


# =========================================================
# AI TUTOR
# =========================================================

AI_TUTOR_SESSION_KEY = "ai_tutor_active_conversation_id"
AI_TUTOR_SESSION_TIMEOUT = timedelta(minutes=30)
AI_TUTOR_PAGE_SIZE = 100


@login_required
def ai_tutor(request):
    if request.method == "POST":
        question = request.POST.get("question", "").strip()
        if not question:
            return JsonResponse(
                {"error": "Enter a question before sending."},
                status=400,
            )

        requested_id = request.POST.get("conversation_id")
        session_id = request.session.get(AI_TUTOR_SESSION_KEY)
        conversation = None
        if requested_id:
            if str(session_id or "") != requested_id:
                return JsonResponse(
                    {"error": "This conversation is no longer active. Select it from history and try again."},
                    status=409,
                )
            conversation = AITutorConversation.objects.filter(
                pk=requested_id,
                user=request.user,
            ).first()
            if conversation is None:
                request.session.pop(AI_TUTOR_SESSION_KEY, None)
                return JsonResponse(
                    {"error": "This conversation is unavailable."},
                    status=404,
                )
        elif session_id:
            conversation = AITutorConversation.objects.filter(
                pk=session_id,
                user=request.user,
            ).first()

        now = timezone.now()
        if conversation and now - conversation.last_active_at > AI_TUTOR_SESSION_TIMEOUT:
            conversation = None
            request.session.pop(AI_TUTOR_SESSION_KEY, None)

        context_messages = []
        if conversation:
            previous_messages = list(
                conversation.messages.order_by("-id")[:20]
            )
            context_messages = list(reversed(previous_messages))

        conversation_text = []
        for message in context_messages:
            speaker = "Student" if message.role == "user" else "AI Tutor"
            conversation_text.append(
                f"{speaker}: {message.content[-4000:]}"
            )
        conversation_text.append(f"Student: {question}")
        prompt = (
            f"You are {settings.SITE_NAME} AI Tutor. "
            "Help students learn programming step by step. "
            "Give clear, beginner-friendly explanations.\n\n"
            "Conversation so far:\n"
            + "\n".join(conversation_text)[-24000:]
        )

        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
            )
            answer = (response.text or "").strip()
            if not answer:
                raise ValueError("The AI provider returned an empty response.")
        except Exception as provider_error:
            logger.error(
                "vGrowHub AI Tutor request failed (%s).",
                type(provider_error).__name__,
                exc_info=True,
            )
            return JsonResponse(
                {"error": "Something went wrong while generating a reply. Please try again."},
                status=502,
            )

        if conversation is None:
            with transaction.atomic():
                conversation = AITutorConversation.objects.create(
                    user=request.user,
                    title=question[:120],
                    last_active_at=now,
                )
                AITutorMessage.objects.bulk_create([
                    AITutorMessage(
                        conversation=conversation,
                        role="user",
                        content=question,
                    ),
                    AITutorMessage(
                        conversation=conversation,
                        role="assistant",
                        content=answer,
                    ),
                ])
        else:
            with transaction.atomic():
                conversation.last_active_at = now
                conversation.save(update_fields=["last_active_at", "updated_at"])
                AITutorMessage.objects.bulk_create([
                    AITutorMessage(
                        conversation=conversation,
                        role="user",
                        content=question,
                    ),
                    AITutorMessage(
                        conversation=conversation,
                        role="assistant",
                        content=answer,
                    ),
                ])
        request.session[AI_TUTOR_SESSION_KEY] = conversation.pk
        return JsonResponse({
            "answer": answer,
            "conversation_id": conversation.pk,
            "title": conversation.title,
        })

    conversation_id = request.session.get(AI_TUTOR_SESSION_KEY)
    conversation = None
    if conversation_id:
        conversation = AITutorConversation.objects.filter(
            pk=conversation_id,
            user=request.user,
        ).first()
        if (
            conversation is None
            or timezone.now() - conversation.last_active_at > AI_TUTOR_SESSION_TIMEOUT
        ):
            request.session.pop(AI_TUTOR_SESSION_KEY, None)
            conversation = None

    current_messages = []
    has_older_messages = False
    if conversation:
        latest = list(conversation.messages.order_by("-id")[:AI_TUTOR_PAGE_SIZE + 1])
        has_older_messages = len(latest) > AI_TUTOR_PAGE_SIZE
        current_messages = list(reversed(latest[:AI_TUTOR_PAGE_SIZE]))

    return render(request, "blog/ai_tutor.html", {
        "conversation": conversation,
        "current_messages": current_messages,
        "has_older_messages": has_older_messages,
    })


@login_required
@require_POST
def ai_tutor_new_chat(request):
    request.session.pop(AI_TUTOR_SESSION_KEY, None)
    return JsonResponse({"ok": True})


@login_required
@require_GET
def ai_tutor_history(request):
    search = request.GET.get("search", "").strip()
    conversations = AITutorConversation.objects.filter(user=request.user)
    if search:
        conversations = conversations.filter(
            Q(title__icontains=search)
            | Q(pk__in=AITutorMessage.objects.filter(
                conversation__user=request.user,
                content__icontains=search,
            ).values("conversation_id"))
        )

    page = Paginator(
        conversations.annotate(message_count=Count("messages")).order_by("-updated_at", "-id"),
        50,
    ).get_page(request.GET.get("page", 1))
    return JsonResponse({
        "items": [{
            "id": item.pk,
            "title": item.title,
            "message_count": item.message_count,
            "updated_at": item.updated_at.isoformat(),
        } for item in page.object_list],
        "page": page.number,
        "num_pages": page.paginator.num_pages,
    })


@login_required
@require_http_methods(["GET", "POST", "DELETE"])
def ai_tutor_conversation(request, conversation_id):
    conversation = AITutorConversation.objects.filter(
        pk=conversation_id,
        user=request.user,
    ).first()
    if conversation is None:
        return JsonResponse({"error": "This conversation is unavailable."}, status=404)

    if request.method == "DELETE":
        conversation.delete()
        if str(request.session.get(AI_TUTOR_SESSION_KEY, "")) == str(conversation_id):
            request.session.pop(AI_TUTOR_SESSION_KEY, None)
        return JsonResponse({"ok": True})

    if request.method == "POST":
        conversation.last_active_at = timezone.now()
        conversation.save(update_fields=["last_active_at", "updated_at"])
        request.session[AI_TUTOR_SESSION_KEY] = conversation.pk

    before_id = request.GET.get("before")
    messages = conversation.messages.all()
    if before_id:
        try:
            messages = messages.filter(pk__lt=int(before_id))
        except (TypeError, ValueError):
            return JsonResponse({"error": "Invalid message cursor."}, status=400)

    latest = list(messages.order_by("-id")[:AI_TUTOR_PAGE_SIZE + 1])
    has_older_messages = len(latest) > AI_TUTOR_PAGE_SIZE
    selected_messages = list(reversed(latest[:AI_TUTOR_PAGE_SIZE]))
    return JsonResponse({
        "conversation_id": conversation.pk,
        "title": conversation.title,
        "messages": [{
            "id": message.pk,
            "role": message.role,
            "content": message.content,
        } for message in selected_messages],
        "has_older_messages": has_older_messages,
        "before_id": selected_messages[0].pk if selected_messages else None,
    })


@login_required
@require_http_methods(["DELETE"])
def ai_tutor_clear_history(request):
    AITutorConversation.objects.filter(user=request.user).delete()
    request.session.pop(AI_TUTOR_SESSION_KEY, None)
    return JsonResponse({"ok": True})


# =========================================================
# PRACTICE
# =========================================================

@login_required
def practice(request):

    progress = {
        item.problem.slug: {
            'status': item.status,
            'attemptCount': item.attempt_count,
            'lastAttemptAt': item.last_attempt_at.isoformat() if item.last_attempt_at else None,
            'solvedAt': item.solved_at.isoformat() if item.solved_at else None,
        }
        for item in PracticeProgress.objects.filter(user=request.user).select_related('problem')
    }
    submissions = [
        {
            'submissionId': item.id,
            'problemId': item.problem.slug,
            'language': item.language,
            'status': item.status,
            'passedTestCases': item.passed_test_cases,
            'totalTestCases': item.total_test_cases,
            'executionTime': item.execution_time,
            'memoryUsed': float(item.memory_used) if item.memory_used is not None else None,
            'submittedAt': item.submitted_at.isoformat(),
        }
        for item in PracticeSubmission.objects.filter(user=request.user).select_related('problem')[:100]
    ]

    return render(
        request,
        'blog/practice.html',
        {
            'username': request.user.username,
            'practice_state': json.dumps({
                'progress': progress,
                'submissions': submissions,
            }),
        }
    )


def _practice_problem(slug):
    return PracticeProblem.objects.get_or_create(
        slug=slug,
        defaults={
            'title': slug.replace('-', ' ').title(),
            'description': '',
            'difficulty': 'EASY',
            'function_name': slug.replace('-', '_'),
        }
    )[0]


def _practice_stats_for_user(user):
    problem_count = PracticeProblem.objects.filter(active=True).count()
    user_progress = {
        item.problem_id: item.status
        for item in PracticeProgress.objects.filter(user=user).select_related('problem')
    }
    solved = sum(value == 'SOLVED' for value in user_progress.values())
    attempted = sum(value == 'ATTEMPTED' for value in user_progress.values())
    completed_tests = MockTestAttempt.objects.filter(
        user=user,
        status__in=('COMPLETED', 'EXPIRED'),
    )
    test_scores = list(completed_tests.values_list('score', 'total_score'))
    percentages = [round(score * 100 / total, 1) for score, total in test_scores if total]
    solved_by_difficulty = {
        row['problem__difficulty'].lower(): row['total']
        for row in PracticeProgress.objects.filter(user=user, status='SOLVED')
        .values('problem__difficulty')
        .annotate(total=Count('id'))
    }
    streak = _learning_streak_for_user(user)

    recent_activity = [
        {
            'title': f'{submission.get_status_display()}: {submission.problem.title}',
            'status': submission.status,
            'created_at': submission.submitted_at,
        }
        for submission in PracticeSubmission.objects.filter(user=user).select_related('problem')[:10]
    ]
    recent_activity.extend(
        {
            'title': f'Completed test: {attempt.test.title}',
            'status': 'COMPLETED',
            'created_at': attempt.submitted_at,
        }
        for attempt in completed_tests.select_related('test').exclude(submitted_at__isnull=True)[:10]
    )
    recent_activity.sort(key=lambda item: item['created_at'], reverse=True)
    completed_durations = completed_tests.exclude(submitted_at__isnull=True)
    return {
        'total_problems': problem_count,
        'solved': solved,
        'attempted': attempted,
        'pending': max(problem_count - solved - attempted, 0),
        'accuracy': round(solved * 100 / problem_count, 1) if problem_count else 0,
        'mock_tests_completed': completed_tests.count(),
        'average_mock_score': round(sum(percentages) / len(percentages), 1) if percentages else 0,
        'best_mock_score': max(percentages, default=0),
        'easy_solved': solved_by_difficulty.get('easy', 0),
        'medium_solved': solved_by_difficulty.get('medium', 0),
        'hard_solved': solved_by_difficulty.get('hard', 0),
        'mock_test_minutes': round(sum(
            max(0, (attempt.submitted_at - attempt.started_at).total_seconds()) / 60
            for attempt in completed_durations
        )),
        'streak': streak,
        'recent_activity': recent_activity[:5],
        'user_progress': user_progress,
    }


@login_required
def practice_details(request):
    stats = _practice_stats_for_user(request.user)
    return render(request, 'blog/practice_details.html', {
        'username': request.user.username,
        'stats': stats,
        'recent_activity': stats['recent_activity'],
    })


@login_required
def practice_all(request):
    problems = PracticeProblem.objects.filter(active=True).order_by('id')
    search = request.GET.get('search', '').strip()[:100]
    category = request.GET.get('category', '').strip()[:40]
    difficulty = request.GET.get('difficulty', '').strip().upper()
    status_filter = request.GET.get('status', '').strip().upper()
    if search:
        problems = problems.filter(Q(title__icontains=search) | Q(description__icontains=search))
    if category:
        problems = problems.filter(Q(category__iexact=category) | Q(tags__icontains=category))
    if difficulty in ('EASY', 'MEDIUM', 'HARD'):
        problems = problems.filter(difficulty=difficulty)
    stats = _practice_stats_for_user(request.user)
    rows = []
    for problem in problems:
        status = stats['user_progress'].get(problem.id, 'NOT_ATTEMPTED')
        if not status_filter or status_filter == status:
            rows.append({'problem': problem, 'status': status})
    categories = PracticeProblem.objects.filter(active=True).values_list('category', flat=True).distinct()
    return render(request, 'blog/practice_all.html', {
        'username': request.user.username,
        'problems': Paginator(rows, 20).get_page(request.GET.get('page')),
        'stats': stats,
        'progress_map': stats['user_progress'],
        'search': search,
        'selected_category': category,
        'selected_difficulty': difficulty,
        'selected_status': status_filter,
        'categories': categories,
    })


@login_required
def practice_playground(request):
    session = None
    if request.GET.get('session'):
        session = get_object_or_404(PlaygroundSession, pk=request.GET['session'], user=request.user)
    languages = supported_languages() if runner_is_configured() else ()
    return render(request, 'blog/practice_playground.html', {
        'username': request.user.username,
        'session': session,
        'languages': languages,
        'selected_language': session.language if session else (languages[0] if languages else ''),
        'sessions': PlaygroundSession.objects.filter(user=request.user)[:10],
        'runner_configured': runner_is_configured(),
    })


@login_required
def practice_mock_tests(request):
    tests = MockTest.objects.filter(active=True).annotate(question_count=Count('questions'))
    latest_by_test = {}
    for attempt in MockTestAttempt.objects.filter(user=request.user).select_related('test'):
        latest_by_test.setdefault(attempt.test_id, attempt)
    return render(request, 'blog/practice_mock_tests.html', {
        'username': request.user.username,
        'tests': [{'test': test, 'attempt': latest_by_test.get(test.id)} for test in tests],
        'stats': _practice_stats_for_user(request.user),
    })


@login_required
def practice_problem_sets(request):
    set_rows = []
    for problem_set in PracticeProblemSet.objects.filter(active=True).prefetch_related('problems'):
        problem_ids = list(problem_set.problems.filter(active=True).values_list('id', flat=True))
        solved = PracticeProgress.objects.filter(
            user=request.user,
            problem_id__in=problem_ids,
            status='SOLVED',
        ).count()
        set_rows.append({
            'set': problem_set,
            'count': len(problem_ids),
            'solved': solved,
            'percent': round(solved * 100 / len(problem_ids)) if problem_ids else 0,
        })
    return render(request, 'blog/practice_problem_sets.html', {
        'username': request.user.username,
        'sets': set_rows,
        'stats': _practice_stats_for_user(request.user),
    })


@login_required
def practice_leaderboard(request):
    period = request.GET.get('period', 'all').lower()
    leaderboard, period = leaderboard_rows(period)
    current_rank = next(
        (rank for rank, row in enumerate(leaderboard, start=1) if row['user'].id == request.user.id),
        None,
    )
    return render(request, 'blog/practice_leaderboard.html', {
        'username': request.user.username,
        'leaderboard': Paginator(leaderboard, 25).get_page(request.GET.get('page')),
        'podium': leaderboard[:3],
        'period': period,
        'current_rank': current_rank,
        'stats': _practice_stats_for_user(request.user),
    })


def _practice_json_payload(request):
    if len(request.body) > 30_000:
        return None
    try:
        payload = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _practice_rate_limited(user):
    cache_key = f'practice-run:{user.pk}'
    if cache.add(cache_key, 1, timeout=60):
        return False
    try:
        return cache.incr(cache_key) > 20
    except ValueError:
        cache.set(cache_key, 1, timeout=60)
        return False


@login_required
def playground_save(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    payload = _practice_json_payload(request)
    if payload is None:
        return JsonResponse({'error': 'Invalid or oversized request.'}, status=400)
    language = str(payload.get('language') or 'text').strip().lower()
    source_code = payload.get('sourceCode', '')
    stdin = payload.get('stdin', '')
    if not isinstance(source_code, str) or len(source_code.encode('utf-8')) > 20_000:
        return JsonResponse({'error': 'Code is larger than the allowed limit.'}, status=400)
    if not isinstance(stdin, str) or len(stdin.encode('utf-8')) > 4_000:
        return JsonResponse({'error': 'Input is larger than the allowed limit.'}, status=400)
    if language not in {'python', 'javascript', 'java', 'text'}:
        return JsonResponse({'error': 'Unsupported session language.'}, status=400)
    session = None
    if payload.get('sessionId'):
        session = get_object_or_404(PlaygroundSession, pk=payload['sessionId'], user=request.user)
    title = str(payload.get('title') or 'Untitled session').strip()[:120] or 'Untitled session'
    if session:
        session.title = title
        session.language = language
        session.source_code = source_code
        session.stdin = stdin
        session.save(update_fields=['title', 'language', 'source_code', 'stdin', 'updated_at'])
    else:
        session = PlaygroundSession.objects.create(
            user=request.user,
            title=title,
            language=language,
            source_code=source_code,
            stdin=stdin,
        )
    return JsonResponse({'saved': True, 'sessionId': session.id})


@login_required
def playground_run(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    payload = _practice_json_payload(request)
    if payload is None:
        return JsonResponse({'error': 'Invalid or oversized request.'}, status=400)
    if _practice_rate_limited(request.user):
        return JsonResponse({'error': 'Execution limit reached. Try again shortly.'}, status=429)
    try:
        result = run_code(
            source_code=payload.get('sourceCode'),
            language=payload.get('language'),
            stdin=payload.get('stdin', ''),
        )
    except CodeRunnerUnavailable as error:
        return JsonResponse({'error': str(error)}, status=503)
    except CodeExecutionError as error:
        return JsonResponse({'error': str(error)}, status=400)
    return JsonResponse(result)


@login_required
def practice_problem_detail(request, slug):
    problem = get_object_or_404(PracticeProblem, slug=slug, active=True)
    progress = PracticeProgress.objects.filter(user=request.user, problem=problem).first()
    history = Paginator(
        PracticeSubmission.objects.filter(user=request.user, problem=problem),
        10,
    ).get_page(request.GET.get('page'))
    language = next(iter(problem.starter_code or {}), '')
    draft = (progress.code_drafts or {}).get(language, '') if progress else ''
    return render(request, 'blog/practice_problem_detail.html', {
        'problem': problem,
        'progress': progress,
        'history': history,
        'language': language,
        'starter_code': draft or (problem.starter_code or {}).get(language, ''),
        'starter_codes': problem.starter_code or {},
        'languages': [item for item in supported_languages() if item in (problem.starter_code or {})]
        if runner_is_configured() else [],
    })


@login_required
def _execute_problem_request(request, slug, submit):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    problem = get_object_or_404(PracticeProblem, slug=slug, active=True)
    payload = _practice_json_payload(request)
    if payload is None:
        return JsonResponse({'error': 'Invalid or oversized request.'}, status=400)
    if _practice_rate_limited(request.user):
        return JsonResponse({'error': 'Execution limit reached. Try again shortly.'}, status=429)
    source_code = payload.get('sourceCode')
    language = str(payload.get('language', '')).strip().lower()
    if language not in supported_languages() or language not in (problem.starter_code or {}):
        return JsonResponse({'error': 'This language is not enabled for this problem.'}, status=400)
    public_tests = problem.public_tests or []
    hidden_tests = (problem.hidden_tests or []) if submit else []
    if any(not isinstance(test_case, dict) for test_case in public_tests + hidden_tests):
        return JsonResponse({'error': 'This problem has invalid test configuration.'}, status=409)
    cases = [dict(test_case, hidden=False) for test_case in public_tests]
    cases.extend(dict(test_case, hidden=True) for test_case in hidden_tests)
    if not cases:
        return JsonResponse({'error': 'This problem has no configured test cases.'}, status=409)
    try:
        result = run_code(
            source_code=source_code,
            language=language,
            function_name=problem.function_name,
            test_cases=cases,
            submit=submit,
        )
    except CodeRunnerUnavailable as error:
        return JsonResponse({'error': str(error)}, status=503)
    except CodeExecutionError as error:
        return JsonResponse({'error': str(error)}, status=400)

    test_results = result['test_results'][:len(cases)]
    passed = sum(bool(item['passed']) for item in test_results)
    accepted = (
        submit
        and result['status'] in ('SUCCESS', 'ACCEPTED')
        and len(test_results) == len(cases)
        and passed == len(cases)
    )
    status = 'ACCEPTED' if accepted else result['status']
    if submit and not accepted and status in ('SUCCESS', 'ACCEPTED'):
        status = 'WRONG_ANSWER'

    with transaction.atomic():
        progress, _ = PracticeProgress.objects.select_for_update().get_or_create(
            user=request.user,
            problem=problem,
        )
        progress.attempt_count += 1
        progress.last_attempt_at = timezone.now()
        if accepted:
            progress.status = 'SOLVED'
            progress.solved_at = progress.solved_at or timezone.now()
        elif progress.status != 'SOLVED':
            progress.status = 'ATTEMPTED'
        progress.save()
        submission = None
        if submit:
            submission = PracticeSubmission.objects.create(
                user=request.user,
                problem=problem,
                language=language,
                source_code=source_code,
                status=status,
                passed_test_cases=passed,
                total_test_cases=len(cases),
                execution_time=result.get('execution_time_ms'),
                memory_used=result.get('memory_kb'),
                result_data={
                    'status': status,
                    'visible_test_results': [item for item in test_results if not item.get('hidden')],
                },
            )
            progress.last_submission = submission
            progress.save(update_fields=['last_submission'])
    return JsonResponse({
        'status': status,
        'passed': passed,
        'total': len(cases),
        'testResults': [item for item in test_results if not item.get('hidden')],
        'stdout': result['stdout'],
        'stderr': result['stderr'],
        'executionTime': result.get('execution_time_ms'),
        'submissionId': submission.id if submission else None,
    })


@login_required
def practice_problem_run(request, slug):
    return _execute_problem_request(request, slug, submit=False)


@login_required
def practice_problem_submit(request, slug):
    return _execute_problem_request(request, slug, submit=True)


@login_required
def practice_problem_set_detail(request, slug):
    problem_set = get_object_or_404(PracticeProblemSet, slug=slug, active=True)
    problems = problem_set.problems.filter(active=True).order_by('id')
    progress = {
        item.problem_id: item.status
        for item in PracticeProgress.objects.filter(user=request.user, problem__in=problems)
    }
    rows = [{'problem': problem, 'status': progress.get(problem.id, 'NOT_ATTEMPTED')} for problem in problems]
    return render(request, 'blog/practice_problem_set_detail.html', {
        'problem_set': problem_set,
        'problems': rows,
        'solved_count': sum(row['status'] == 'SOLVED' for row in rows),
    })


@login_required
def practice_mock_test_detail(request, pk):
    mock_test = get_object_or_404(MockTest, pk=pk, active=True)
    questions = mock_test.questions.all()
    attempts = MockTestAttempt.objects.filter(user=request.user, test=mock_test)
    latest_attempt = attempts.first()
    return render(request, 'blog/practice_mock_test_detail.html', {
        'mock_test': mock_test,
        'question_count': questions.count(),
        'total_points': sum(questions.values_list('points', flat=True)),
        'latest_attempt': latest_attempt,
        'can_start': bool(questions.exists()) and (
            mock_test.allow_retakes
            or not attempts.filter(status__in=('COMPLETED', 'EXPIRED')).exists()
        ),
    })


@login_required
def practice_mock_test_start(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    mock_test = get_object_or_404(MockTest, pk=pk, active=True)
    if not mock_test.questions.exists():
        return JsonResponse({'error': 'This test has no questions yet.'}, status=409)
    attempts = MockTestAttempt.objects.filter(user=request.user, test=mock_test)
    active_attempt = attempts.filter(status='IN_PROGRESS').first()
    if active_attempt:
        return redirect('blog:practice_mock_test_attempt', pk=active_attempt.pk)
    if not mock_test.allow_retakes:
        completed_attempt = attempts.filter(status__in=('COMPLETED', 'EXPIRED')).first()
        if completed_attempt:
            return redirect('blog:practice_mock_test_result', pk=completed_attempt.pk)
    attempt = MockTestAttempt.objects.create(
        user=request.user,
        test=mock_test,
        expires_at=timezone.now() + timedelta(minutes=mock_test.duration_minutes),
        total_score=sum(mock_test.questions.values_list('points', flat=True)),
    )
    return redirect('blog:practice_mock_test_attempt', pk=attempt.pk)


def _finalize_mock_attempt(attempt, expired=False):
    if attempt.status != 'IN_PROGRESS':
        return attempt
    questions = attempt.test.questions.all()
    attempt.score = sum(
        question.points
        for question in questions
        if attempt.answers.get(str(question.id)) is not None
        and str(attempt.answers[str(question.id)]) == str(question.correct_answer)
    )
    attempt.total_score = sum(question.points for question in questions)
    attempt.submitted_at = timezone.now()
    attempt.status = 'EXPIRED' if expired else 'COMPLETED'
    attempt.save(update_fields=['score', 'total_score', 'submitted_at', 'status'])
    return attempt


@login_required
def practice_mock_test_attempt(request, pk):
    attempt = get_object_or_404(
        MockTestAttempt.objects.select_related('test'),
        pk=pk,
        user=request.user,
    )
    if attempt.status != 'IN_PROGRESS':
        return redirect('blog:practice_mock_test_result', pk=attempt.pk)
    with transaction.atomic():
        attempt = MockTestAttempt.objects.select_for_update().get(pk=attempt.pk, user=request.user)
        if timezone.now() >= attempt.expires_at:
            _finalize_mock_attempt(attempt, expired=True)
    if attempt.status != 'IN_PROGRESS':
        return redirect('blog:practice_mock_test_result', pk=attempt.pk)
    questions = [
        {'question': question, 'answer': attempt.answers.get(str(question.id), '')}
        for question in attempt.test.questions.all()
    ]
    return render(request, 'blog/practice_mock_test_attempt.html', {
        'attempt': attempt,
        'questions': questions,
        'remaining_seconds': max(0, int((attempt.expires_at - timezone.now()).total_seconds())),
    })


@login_required
def practice_mock_test_answer(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    payload = _practice_json_payload(request)
    if payload is None:
        return JsonResponse({'error': 'Invalid request.'}, status=400)
    with transaction.atomic():
        attempt = get_object_or_404(
            MockTestAttempt.objects.select_for_update().select_related('test'),
            pk=pk,
            user=request.user,
        )
        if attempt.status != 'IN_PROGRESS':
            return JsonResponse({'error': 'This test attempt is already closed.'}, status=409)
        if timezone.now() >= attempt.expires_at:
            _finalize_mock_attempt(attempt, expired=True)
            return JsonResponse({'error': 'Time expired. The test was finalized.'}, status=409)
        question = get_object_or_404(
            MockTestQuestion,
            pk=payload.get('questionId'),
            test=attempt.test,
        )
        answer = str(payload.get('answer', ''))[:500]
        option_ids = {
            str(option.get('id', ''))
            for option in question.options
            if isinstance(option, dict)
        }
        if answer and answer not in option_ids:
            return JsonResponse({'error': 'Choose a valid answer.'}, status=400)
        answers = dict(attempt.answers or {})
        if answer:
            answers[str(question.id)] = answer
        else:
            answers.pop(str(question.id), None)
        attempt.answers = answers
        attempt.save(update_fields=['answers'])
    return JsonResponse({'saved': True})


@login_required
def practice_mock_test_submit(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    with transaction.atomic():
        attempt = get_object_or_404(
            MockTestAttempt.objects.select_for_update(),
            pk=pk,
            user=request.user,
        )
        if attempt.status != 'IN_PROGRESS':
            return JsonResponse({'error': 'This test has already been submitted.'}, status=409)
        _finalize_mock_attempt(attempt, expired=timezone.now() >= attempt.expires_at)
    return redirect('blog:practice_mock_test_result', pk=attempt.pk)


@login_required
def practice_mock_test_result(request, pk):
    attempt = get_object_or_404(
        MockTestAttempt.objects.select_related('test'),
        pk=pk,
        user=request.user,
    )
    if attempt.status == 'IN_PROGRESS':
        return redirect('blog:practice_mock_test_attempt', pk=attempt.pk)
    question_rows = []
    for question in attempt.test.questions.all():
        answer = attempt.answers.get(str(question.id))
        correct = answer is not None and str(answer) == str(question.correct_answer)
        correct_option = next((
            option for option in question.options
            if isinstance(option, dict) and str(option.get('id')) == str(question.correct_answer)
        ), None)
        selected_option = next((
            option for option in question.options
            if isinstance(option, dict) and str(option.get('id')) == str(answer)
        ), None)
        question_rows.append({
            'question': question,
            'answer': answer,
            'correct': correct,
            'selected_option': selected_option,
            'correct_option': correct_option,
        })
    elapsed_seconds = max(0, int(((attempt.submitted_at or timezone.now()) - attempt.started_at).total_seconds()))
    answered_count = sum(row['answer'] is not None for row in question_rows)
    correct_count = sum(row['correct'] for row in question_rows)
    return render(request, 'blog/practice_mock_test_result.html', {
        'attempt': attempt,
        'question_rows': question_rows,
        'answered_count': answered_count,
        'correct_count': correct_count,
        'incorrect_count': answered_count - correct_count,
        'unanswered_count': len(question_rows) - answered_count,
        'elapsed_seconds': elapsed_seconds,
        'elapsed_minutes': elapsed_seconds // 60,
        'elapsed_remainder': elapsed_seconds % 60,
        'review_mode': request.GET.get('review') == '1',
    })


@login_required
def practice_save_draft(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    payload = json.loads(request.body or '{}')
    problem = _practice_problem(payload.get('problemId', ''))
    progress, _ = PracticeProgress.objects.get_or_create(
        user=request.user,
        problem=problem,
    )
    drafts = progress.code_drafts or {}
    drafts[payload.get('language', 'python')] = payload.get('sourceCode', '')
    progress.code_drafts = drafts
    progress.save(update_fields=['code_drafts'])
    return JsonResponse({'saved': True})


@login_required
def practice_record(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    payload = json.loads(request.body or '{}')
    problem = _practice_problem(payload.get('problemId', ''))
    is_submission = payload.get('kind') == 'submit'
    status = payload.get('status', 'INTERNAL_ERROR')
    progress, _ = PracticeProgress.objects.get_or_create(
        user=request.user,
        problem=problem,
    )
    progress.attempt_count += 1
    progress.last_attempt_at = timezone.now()
    if is_submission and status == 'ACCEPTED':
        progress.status = 'SOLVED'
        progress.solved_at = progress.solved_at or timezone.now()
    elif progress.status != 'SOLVED':
        progress.status = 'ATTEMPTED'
    progress.save()

    submission = None
    if is_submission:
        submission = PracticeSubmission.objects.create(
            user=request.user,
            problem=problem,
            language=payload.get('language', ''),
            source_code=payload.get('sourceCode', ''),
            status=status,
            passed_test_cases=payload.get('passed', 0) or 0,
            total_test_cases=payload.get('total', 0) or 0,
            execution_time=payload.get('runtime'),
            memory_used=payload.get('memory'),
            result_data={
                'status': status,
                'passed': payload.get('passed', 0),
                'total': payload.get('total', 0),
            },
        )
        progress.last_submission = submission
        progress.save(update_fields=['last_submission'])
    return JsonResponse({
        'saved': True,
        'status': progress.status,
        'submissionId': submission.id if submission else None,
    })


# =========================================================
# ASSIGNMENTS
# =========================================================

@login_required
def assignments(request):
    assignments_qs = _eligible_assignments(request.user)
    status_filter = request.GET.get('status', 'all').upper()
    source_filter = request.GET.get('source', 'all').upper()
    search = request.GET.get('search', '').strip()
    if source_filter in ('STANDALONE', 'COURSE'):
        assignments_qs = assignments_qs.filter(assignment_source=source_filter)
    if search:
        assignments_qs = assignments_qs.filter(title__icontains=search)

    progress_records = {
        item.assignment_id: item
        for item in UserAssignmentProgress.objects.filter(
            user=request.user,
            assignment__in=assignments_qs
        )
    }
    visible = []
    for item in assignments_qs:
        item.user_progress = progress_records.get(item.id)
        item.display_status = item.user_progress.status if item.user_progress else 'PENDING'
        if status_filter == 'PENDING' and item.user_progress and item.user_progress.status not in ('NOT_STARTED', 'IN_PROGRESS'):
            continue
        if status_filter == 'SUBMITTED' and (not item.user_progress or item.user_progress.status != 'SUBMITTED'):
            continue
        if status_filter == 'EVALUATED' and (not item.user_progress or item.user_progress.status not in ('EVALUATED', 'PASSED', 'FAILED')):
            continue
        if status_filter == 'OVERDUE' and (not item.due_date or item.due_date >= timezone.now()):
            continue
        visible.append(item)

    completed = sum(item.display_status in ('EVALUATED', 'PASSED') for item in visible)
    pending = sum(item.display_status in ('PENDING', 'NOT_STARTED', 'IN_PROGRESS') for item in visible)
    submitted = sum(item.display_status == 'SUBMITTED' for item in visible)
    deadlines = [item for item in visible if item.due_date and item.due_date >= timezone.now()]
    next_deadline = min(deadlines, key=lambda item: item.due_date) if deadlines else None
    return render(
        request,
        'blog/assignments.html',
        {
            'username': request.user.username,
            'assignments': visible,
            'total_assignments': len(visible),
            'pending_count': pending,
            'submitted_count': submitted,
            'completed_count': completed,
            'next_deadline': next_deadline,
            'status_filter': status_filter.lower(),
            'source_filter': source_filter.lower(),
            'search': search,
        }
    )


@login_required
def assignment_attempt(request, pk):
    assignment = get_object_or_404(Assignment.objects.select_related('course', 'lesson__course'), pk=pk)
    if not _can_access_assignment(request.user, assignment):
        return HttpResponseForbidden('You do not have access to this assignment.')

    progress, _ = UserAssignmentProgress.objects.get_or_create(
        user=request.user,
        assignment=assignment
    )
    attempt = progress.latest_attempt
    start_new_attempt = request.GET.get('new') == '1'
    if not attempt or (start_new_attempt and attempt.status != 'IN_PROGRESS'):
        if progress.attempts_used >= assignment.max_attempts:
            if not attempt:
                return HttpResponseForbidden('No attempts remaining.')
            start_new_attempt = False
        else:
            start_new_attempt = True

    if start_new_attempt and (not attempt or attempt.status != 'IN_PROGRESS'):
        attempt = AssignmentAttempt.objects.create(
            assignment=assignment,
            user=request.user,
            attempt_number=progress.attempts_used + 1,
            max_score=assignment.max_score,
        )
        progress.latest_attempt = attempt
        progress.attempts_used += 1
        progress.status = 'IN_PROGRESS'
        progress.started_at = progress.started_at or timezone.now()
        progress.save()

    if request.method == 'POST':
        if attempt.status != 'IN_PROGRESS':
            return JsonResponse({'error': 'This attempt was already submitted.'}, status=409)

        try:
            answer_data = json.loads(request.POST.get('answer_data', '{}'))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Invalid answer data.'}, status=400)
        if not isinstance(answer_data, dict):
            return JsonResponse({'error': 'Answers must be an object.'}, status=400)

        if request.POST.get('action') == 'save':
            attempt.answer_data = answer_data
            attempt.source_code = request.POST.get('source_code', '')
            attempt.language = request.POST.get('language', '')
            attempt.save()
            return JsonResponse({'saved': True})

        if assignment.due_date and assignment.due_date < timezone.now() and not assignment.late_submission_allowed:
            return render(request, 'blog/assignment_attempt.html', {
                'assignment': assignment,
                'attempt': attempt,
                'questions': assignment.questions.prefetch_related('options').all(),
                'error_message': 'The deadline has passed and late submissions are not allowed.',
            }, status=403)

        uploaded_file = request.FILES.get('file')
        if assignment.assignment_type == 'FILE_UPLOAD' and not uploaded_file and not attempt.answer_data.get('file_name'):
            return render(request, 'blog/assignment_attempt.html', {
                'assignment': assignment,
                'attempt': attempt,
                'questions': assignment.questions.prefetch_related('options').all(),
                'error_message': 'Choose a file before submitting.',
            }, status=400)

        attempt.answer_data = answer_data
        attempt.source_code = request.POST.get('source_code', '')
        attempt.language = request.POST.get('language', '')
        attempt.status = 'SUBMITTED'
        attempt.submitted_at = timezone.now()
        if assignment.assignment_type == 'QUIZ':
            score = 0
            for question in assignment.questions.prefetch_related('options'):
                selected = answer_data.get(str(question.id), [])
                if not isinstance(selected, list):
                    selected = [selected]
                correct = list(question.options.filter(is_correct=True).values_list('id', flat=True))
                if sorted(map(str, selected)) == sorted(map(str, correct)):
                    score += question.marks
            attempt.score = score
            attempt.max_score = sum(q.marks for q in assignment.questions.all()) or assignment.max_score
            attempt.percentage = round(score * 100 / attempt.max_score) if attempt.max_score else 0
            attempt.passed = score >= assignment.passing_marks
            attempt.status = 'EVALUATED'
            attempt.evaluated_at = timezone.now()
            progress.status = 'PASSED' if attempt.passed else 'FAILED'
            progress.completed_at = timezone.now() if attempt.passed else None
            progress.evaluated_at = timezone.now()
            progress.best_score = max(progress.best_score or 0, score)
        else:
            progress.status = 'SUBMITTED'
            response = answer_data.get('response', '')
            submission = AssignmentSubmission(
                assignment=assignment,
                student=request.user,
                answer=attempt.source_code or response,
            )
            if uploaded_file:
                submission.file.save(uploaded_file.name, uploaded_file, save=False)
                answer_data['file_name'] = uploaded_file.name
                attempt.answer_data = answer_data
            submission.save()
        progress.submitted_at = timezone.now()
        progress.save()
        attempt.save()
        return redirect('blog:assignment_attempt', pk=assignment.pk)

    return render(request, 'blog/assignment_attempt.html', {
        'assignment': assignment,
        'attempt': attempt,
        'questions': assignment.questions.prefetch_related('options').all(),
        'submission': AssignmentSubmission.objects.filter(
            assignment=assignment,
            student=request.user,
        ).order_by('-submitted_at').first(),
        'can_retry': attempt.status != 'IN_PROGRESS' and progress.attempts_used < assignment.max_attempts,
    })


# =========================================================
# PROJECT LIST
# =========================================================

@login_required
def projects(request):

    search = request.GET.get(
        'search',
        ''
    ).strip()

    category = request.GET.get(
        'category',
        ''
    ).strip()

    status = request.GET.get(
        'status',
        ''
    ).strip()

    tab = request.GET.get(
        'tab',
        'discover'
    )

    projects_queryset = Project.objects.all().select_related(
        'owner'
    ).prefetch_related(
        'images'
    ).order_by(
        '-created_at'
    ).filter(
        _user_content_visibility_filter('owner', request.user)
    )

    if search:

        projects_queryset = projects_queryset.filter(
            title__icontains=search
        ) | projects_queryset.filter(
            short_description__icontains=search
        )

    if category:

        projects_queryset = projects_queryset.filter(
            category__iexact=category
        )

    if status:

        projects_queryset = projects_queryset.filter(
            status=status
        )

    if tab == 'my':

        projects_queryset = projects_queryset.filter(
            owner=request.user
        )

    elif tab == 'saved':

        projects_queryset = projects_queryset.filter(
            saves__user=request.user
        )

    context = {
        'projects': projects_queryset,
        'username': request.user.username,
        'search': search,
        'category': category,
        'status': status,
        'tab': tab,
    }

    return render(
        request,
        'blog/projects.html',
        context
    )


# =========================================================
# CREATE PROJECT
# =========================================================

@login_required
def create_project(request):

    if request.method == "POST":

        form = ProjectForm(
            request.POST
        )

        if form.is_valid():

            project = form.save(
                commit=False
            )

            project.owner = request.user

            project.original_description = (
                project.description
            )

            project.save()

            images = request.FILES.getlist(
                'images'
            )

            for image in images:

                ProjectImage.objects.create(
                    project=project,
                    image=image
                )

            return redirect(
                'blog:project_detail',
                pk=project.pk
            )

    else:

        form = ProjectForm()

    return render(
        request,
        'blog/project_form.html',
        {
            'form': form,
            'username': request.user.username,
        }
    )


# =========================================================
# PROJECT DETAIL
# =========================================================

@login_required
def project_detail(request, pk):

    project = get_object_or_404(
        Project.objects.select_related(
            'owner'
        ).prefetch_related(
            'images',
            'updates',
            'collaborators'
        ),
        pk=pk
    )

    ProjectView.objects.create(
        project=project,
        user=request.user
    )

    is_liked = ProjectLike.objects.filter(
        project=project,
        user=request.user
    ).exists()

    is_saved = ProjectSave.objects.filter(
        project=project,
        user=request.user
    ).exists()

    is_following = ProjectFollow.objects.filter(
        project=project,
        user=request.user
    ).exists()

    comments = ProjectComment.objects.filter(
        project=project
    ).select_related(
        'user'
    ).prefetch_related(
        'likes'
    ).order_by(
        '-created_at'
    )

    context = {
        'project': project,
        'comments': comments,
        'is_liked': is_liked,
        'is_saved': is_saved,
        'is_following': is_following,
        'like_count': project.likes.count(),
        'save_count': project.saves.count(),
        'follower_count': project.followers.count(),
        'view_count': project.views.count(),
        'username': request.user.username,
    }

    return render(
        request,
        'blog/project_detail.html',
        context
    )


# =========================================================
# LIKE PROJECT
# =========================================================

@login_required
def project_like(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if request.method == "POST":
        like, created = ProjectLike.objects.get_or_create(
            project=project,
            user=request.user
        )

        if not created:
            like.delete()
            liked = False
        else:
            liked = True

        return JsonResponse({
            "success": True,
            "liked": liked,
            "count": project.likes.count(),
        })

    return JsonResponse({
        "success": False,
        "error": "Invalid request"
    }, status=400)

# =========================================================
# SAVE PROJECT
# =========================================================

@login_required
def project_save(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if request.method == "POST":
        saved, created = ProjectSave.objects.get_or_create(
            project=project,
            user=request.user
        )

        if not created:
            saved.delete()
            is_saved = False
        else:
            is_saved = True

        return JsonResponse({
            "success": True,
            "saved": is_saved,
            "count": project.saves.count(),
        })

    return JsonResponse({
        "success": False,
        "error": "Invalid request"
    }, status=400)

# =========================================================
# FOLLOW PROJECT
# =========================================================

@login_required
def project_follow(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if request.method == "POST":
        follow, created = ProjectFollow.objects.get_or_create(
            project=project,
            user=request.user
        )

        if not created:
            follow.delete()
            following = False
        else:
            following = True

        return JsonResponse({
            "success": True,
            "following": following,
            "count": project.follows.count(),
        })

    return JsonResponse({
        "success": False,
        "error": "Invalid request"
    }, status=400)

    
# =========================================================
# PROJECT COMMENT
# =========================================================

@login_required
def project_comment(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if request.method == "POST":

        content = request.POST.get("content", "").strip()

        if not content:
            return JsonResponse({
                "success": False,
                "error": "Comment cannot be empty."
            }, status=400)

        comment = ProjectComment.objects.create(
            project=project,
            user=request.user,
            content=content
        )

        return JsonResponse({
            "success": True,
            "comment": {
                "id": comment.id,
                "username": comment.user.username,
                "initial": comment.user.username[0].upper(),
                "content": comment.content,
                "date": comment.created_at.strftime("%b %d, %Y"),
            },
            "count": project.comments.count(),
        })

    return JsonResponse({
        "success": False,
        "error": "Invalid request"
    }, status=400)

# =========================================================
# PROJECT COMMENT LIKE
# =========================================================

@login_required
def project_comment_like(request, pk):

    comment = get_object_or_404(
        ProjectComment,
        pk=pk
    )

    like = ProjectCommentLike.objects.filter(
        comment=comment,
        user=request.user
    ).first()

    if like:

        like.delete()

    else:

        ProjectCommentLike.objects.create(
            comment=comment,
            user=request.user
        )

    return redirect(
        'blog:project_detail',
        pk=comment.project.pk
    )


# =========================================================
# PROJECT UPDATE
# =========================================================

@login_required
def project_update(request, pk):

    project = get_object_or_404(
        Project,
        pk=pk
    )

    if request.user != project.owner:

        return redirect(
            'blog:project_detail',
            pk=project.pk
        )

    if request.method == "POST":

        title = request.POST.get(
            'title',
            ''
        ).strip()

        content = request.POST.get(
            'content',
            ''
        ).strip()

        if title and content:

            ProjectUpdate.objects.create(
                project=project,
                title=title,
                content=content
            )

    return redirect(
        'blog:project_detail',
        pk=project.pk
    )


# =========================================================
# PROJECT COLLABORATOR REQUEST
# =========================================================

@login_required
def project_collaborate(request, pk):

    project = get_object_or_404(
        Project,
        pk=pk
    )

    if request.method != "POST":

        return JsonResponse({
            "success": False,
            "error": "Invalid request."
        }, status=400)

    if request.user == project.owner:

        return JsonResponse({
            "success": False,
            "error": "You cannot collaborate on your own project."
        }, status=403)

    ProjectCollaborator.objects.get_or_create(
        project=project,
        user=request.user,
        defaults={
            "role": "Interested"
        }
    )

    return JsonResponse({
        "success": True,
        "interested": True,
        "show_connect": True,
        "message": "Your interest has been recorded."
    })


@login_required
def project_connect(request, pk):

    project = get_object_or_404(
        Project,
        pk=pk
    )

    if request.method != "POST":

        return JsonResponse({
            "success": False,
            "error": "Invalid request."
        }, status=400)

    if request.user == project.owner:

        return JsonResponse({
            "success": False,
            "error": "You cannot connect with yourself."
        }, status=400)
    if _users_blocked(request.user, project.owner):
        return JsonResponse({'success': False, 'error': 'This action is unavailable.'}, status=403)

    conversation = Conversation.objects.filter(
        project=project,
        project_owner=project.owner,
        participant=request.user
    ).first()

    if conversation is None:

        conversation = Conversation.objects.create(
            project=project,
            project_owner=project.owner,
            participant=request.user
        )

    return JsonResponse({
        "success": True,
        "conversation_id": conversation.id,
        "redirect_url": reverse(
            "blog:conversation_detail",
            args=[conversation.id]
        ),
        "message": "Conversation ready."
    })


@login_required
def messages_list(request):

    conversations = Conversation.objects.filter(
        Q(project_owner=request.user) |
        Q(participant=request.user)
    ).select_related(
        "project",
        "project_owner__profile_data",
        "participant__profile_data"
    ).prefetch_related(
        "messages__sender"
    ).order_by(
        "-updated_at"
    )
    blocked_user_ids = UserBlock.objects.filter(
        blocker=request.user
    ).values_list('blocked_id', flat=True).union(
        UserBlock.objects.filter(
            blocked=request.user
        ).values_list('blocker_id', flat=True)
    )
    conversations = conversations.exclude(
        project_owner_id__in=blocked_user_ids
    ).exclude(
        participant_id__in=blocked_user_ids
    )
    conversations = [
        conversation
        for conversation in conversations
        if conversation.project_id is not None
        or _can_message_between(
            request.user,
            conversation.participant
            if conversation.project_owner_id == request.user.id
            else conversation.project_owner,
        )
    ]

    for conversation in conversations:

        conversation.unread_count = conversation.messages.filter(
            is_read=False
        ).exclude(
            sender=request.user
        ).count()

        last_message = conversation.messages.order_by(
            "-created_at"
        ).first()

        conversation.last_message = last_message

        if last_message:

            conversation.last_message_time = (
                last_message.created_at.strftime(
                    "%I:%M %p"
                )
            )

        else:

            conversation.last_message_time = ""

    accepted_following_ids = FollowRequest.objects.filter(
        sender=request.user,
        status='ACCEPTED',
    ).values_list('receiver_id', flat=True)
    mutual_contact_ids = FollowRequest.objects.filter(
        sender_id__in=accepted_following_ids,
        receiver=request.user,
        status='ACCEPTED',
    ).values_list('sender_id', flat=True)
    available_users = User.objects.filter(
        id__in=mutual_contact_ids,
    ).exclude(
        id__in=blocked_user_ids,
    ).order_by(
        "username"
    ).select_related("profile_data")

    return render(
        request,
        "blog/messages.html",
        {
            "conversations": conversations,
            "available_users": available_users,
        }
    )


@login_required
def discover_users(request):
    query = request.GET.get('q', '').strip()
    username_query = query.removeprefix('@').strip()
    blocked_user_ids = UserBlock.objects.filter(
        blocker=request.user
    ).values_list('blocked_id', flat=True).union(
        UserBlock.objects.filter(
            blocked=request.user
        ).values_list('blocker_id', flat=True)
    )
    users = []
    if username_query:
        users = list(User.objects.filter(
            Q(username__icontains=username_query)
            | Q(profile_data__display_name__icontains=username_query)
        ).filter(
            profile_data__is_deactivated=False,
            profile_data__scheduled_deletion_at__isnull=True,
        ).exclude(
            id=request.user.id
        ).exclude(
            id__in=blocked_user_ids
        ).select_related(
            'profile_data'
        ).order_by(
            'username'
        )[:50])

        user_ids = [person.id for person in users]
        following_ids = set(FollowRequest.objects.filter(
            sender=request.user,
            receiver_id__in=user_ids,
            status='ACCEPTED',
        ).values_list('receiver_id', flat=True))
        follower_ids = set(FollowRequest.objects.filter(
            sender_id__in=user_ids,
            receiver=request.user,
            status='ACCEPTED',
        ).values_list('sender_id', flat=True))
        pending_ids = set(FollowRequest.objects.filter(
            sender=request.user,
            receiver_id__in=user_ids,
            status='PENDING',
        ).values_list('receiver_id', flat=True))

        for person in users:
            person.can_message = (
                person.id in following_ids and person.id in follower_ids
            )
            person.relationship_status = (
                'following' if person.id in following_ids
                else 'requested' if person.id in pending_ids
                else 'follow_back' if person.id in follower_ids
                else 'follow'
            )

    return render(request, 'blog/discover_users.html', {
        'query': query,
        'users': users,
    })


# @login_required
@login_required
def conversation_detail(request, conversation_id):

    conversation = get_object_or_404(
        Conversation.objects.select_related(
            "project",
            "project_owner__profile_data",
            "participant__profile_data"
        ).prefetch_related(
            "messages__sender",
            "messages__sender__profile_data",
            "messages__attachments"
        ),
        id=conversation_id
    )


    # =====================================================
    # CHECK ACCESS
    # =====================================================

    if (
        request.user != conversation.project_owner
        and request.user != conversation.participant
    ):

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "You are not allowed to access "
                    "this conversation."
                )
            },
            status=403
        )


    # =====================================================
    # FIND OTHER USER
    # =====================================================

    if request.user == conversation.project_owner:

        chat_user = conversation.participant

    else:

        chat_user = conversation.project_owner

    if _users_blocked(request.user, chat_user):
        return JsonResponse({
            'success': False,
            'error': 'This conversation is unavailable.',
        }, status=403)
    if (
        conversation.project_id is None
        and not _can_message_between(request.user, chat_user)
    ):
        return JsonResponse({
            'success': False,
            'error': 'This conversation is available to mutual followers only.',
        }, status=403)


    # =====================================================
    # POST - SEND MESSAGE / FILE
    # =====================================================

    if request.method == "POST":

        content = request.POST.get(
            "content",
            ""
        ).strip()


        uploaded_files = request.FILES.getlist(
            "attachments"
        )


        # Message and files both empty
        if not content and not uploaded_files:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Message cannot be empty."
                },
                status=400
            )


        # -------------------------------------------------
        # CREATE MESSAGE
        # -------------------------------------------------

        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=content,
            is_delivered=False,
            is_read=False
        )


        # -------------------------------------------------
        # SAVE FILES
        # -------------------------------------------------

        for uploaded_file in uploaded_files:

            MessageAttachment.objects.create(
                message=message,
                file=uploaded_file,
                original_name=uploaded_file.name
            )


        # -------------------------------------------------
        # UPDATE CONVERSATION
        # -------------------------------------------------

        conversation.save(
            update_fields=[
                "updated_at"
            ]
        )

        try:
            async_to_sync(get_channel_layer().group_send)(
                f'conversation_{conversation.id}',
                {
                    'type': 'chat.message',
                    'message_id': message.id,
                },
            )
        except Exception:
            logger.exception(
                'Could not broadcast persisted message %s to its conversation.',
                message.id,
            )


        # -------------------------------------------------
        # ATTACHMENT RESPONSE
        # -------------------------------------------------

        attachments = []


        for attachment in message.attachments.all():

            attachments.append(
                {
                    "id": attachment.id,
                    "url": attachment.file.url,
                    "name": attachment.original_name
                }
            )


        # -------------------------------------------------
        # JSON RESPONSE
        # -------------------------------------------------

        return JsonResponse(
            {
                "success": True,

                "message": {

                    "id": message.id,

                    "content": message.content,

                    "sender": message.sender.username,

                    "is_me": True,

                    "is_delivered": (
                        message.is_delivered
                    ),

                    "is_read": (
                        message.is_read
                    ),

                    "created_at": (
                        message.created_at.strftime(
                            "%d %b %Y, %I:%M %p"
                        )
                    ),

                    "attachments": attachments
                }
            }
        )


    # =====================================================
    # GET - OPEN CHAT
    # =====================================================

    conversation.messages.filter(
        is_delivered=False
    ).exclude(
        sender=request.user
    ).update(
        is_delivered=True
    )


    conversation.messages.filter(
        is_read=False
    ).exclude(
        sender=request.user
    ).update(
        is_read=True
    )


    # =====================================================
    # GET ALL MESSAGES
    # =====================================================

    messages = conversation.messages.select_related(
    "sender",
    "sender__profile_data"
        ).prefetch_related(
            "attachments"
        ).exclude(
            deleted_for_users=request.user
        ).all()

    # =====================================================
    # RENDER CHAT
    # =====================================================

    return render(
        request,
        "blog/conversation.html",
        {
            "conversation": conversation,

            "messages": messages,

            "chat_user": chat_user,

            "chat_user_id": chat_user.id,

            "username": request.user.username,
        }
    )
    

# =========================================================
# DELETE MESSAGE
# =========================================================

# =========================================================
# DELETE MESSAGE
# =========================================================

@login_required
def delete_message(request, message_id):

    if request.method != "POST":
        return JsonResponse({
            "success": False,
            "error": "Invalid request."
        }, status=400)

    message = get_object_or_404(
        Message,
        id=message_id
    )

    # Check conversation access
    if (
        request.user != message.conversation.project_owner
        and request.user != message.conversation.participant
    ):
        return JsonResponse({
            "success": False,
            "error": "You are not allowed to delete this message."
        }, status=403)

    chat_user = (
        message.conversation.participant
        if request.user == message.conversation.project_owner
        else message.conversation.project_owner
    )
    if _users_blocked(request.user, chat_user) or (
        message.conversation.project_id is None
        and not _can_message_between(request.user, chat_user)
    ):
        return JsonResponse({
            "success": False,
            "error": "This conversation is unavailable."
        }, status=403)

    delete_type = request.POST.get(
        "delete_type",
        ""
    )

    # =====================================================
    # DELETE FOR ME
    # =====================================================

    if delete_type == "me":

        message.deleted_for_users.add(
            request.user
        )

        return JsonResponse({
            "success": True,
            "delete_type": "me",
            "message_id": message.id
        })

    # =====================================================
    # DELETE FOR EVERYONE
    # =====================================================

    if delete_type == "everyone":

        # Only sender can delete for everyone
        if message.sender != request.user:
            return JsonResponse({
                "success": False,
                "error": (
                    "Only the sender can delete "
                    "this message for everyone."
                )
            }, status=403)

        message.deleted_for_everyone = True
        message.content = ""

        message.save(
            update_fields=[
                "deleted_for_everyone",
                "content"
            ]
        )

        # Remove attachments
        message.attachments.all().delete()

        return JsonResponse({
            "success": True,
            "delete_type": "everyone",
            "message_id": message.id
        })

    return JsonResponse({
        "success": False,
        "error": "Invalid delete option."
    }, status=400)


@login_required
def conversation_status(request, conversation_id):

    conversation = get_object_or_404(
        Conversation,
        id=conversation_id
    )

    if (
        request.user != conversation.project_owner
        and request.user != conversation.participant
    ):

        return JsonResponse({
            "success": False,
            "error": "You are not allowed to access this conversation."
        }, status=403)

    chat_user = (
        conversation.participant
        if request.user == conversation.project_owner
        else conversation.project_owner
    )
    if _users_blocked(request.user, chat_user) or (
        conversation.project_id is None
        and not _can_message_between(request.user, chat_user)
    ):
        return JsonResponse({
            "success": False,
            "error": "This conversation is unavailable."
        }, status=403)

    conversation.messages.filter(
        is_delivered=False
    ).exclude(
        sender=request.user
    ).update(
        is_delivered=True
    )

    conversation.messages.filter(
        is_read=False
    ).exclude(
        sender=request.user
    ).update(
        is_read=True
    )

    message_records = conversation.messages.select_related(
        'sender__profile_data',
    ).prefetch_related(
        'attachments',
    ).exclude(
        deleted_for_users=request.user,
    )
    messages = []
    for message in message_records:
        profile = message.sender.profile_data
        messages.append({
            'id': message.id,
            'sender_id': message.sender_id,
            'sender_username': message.sender.username,
            'sender_display_name': profile.display_name or message.sender.username,
            'sender_profile_picture': (
                profile.profile_picture.url
                if profile.profile_picture
                else ''
            ),
            'content': message.content,
            'is_delivered': message.is_delivered,
            'is_read': message.is_read,
            'deleted_for_everyone': message.deleted_for_everyone,
            'created_at': timezone.localtime(message.created_at).strftime(
                '%d %b %Y, %I:%M %p'
            ),
            'attachments': [
                {
                    'url': attachment.file.url,
                    'name': attachment.original_name,
                }
                for attachment in message.attachments.all()
            ],
        })

    return JsonResponse({
        "success": True,
        "messages": list(messages)
    })

@login_required
def project_report(request, pk):

    project = get_object_or_404(
        Project,
        pk=pk
    )

    if request.method == "POST":

        reason = request.POST.get(
            'reason',
            ''
        ).strip()

        description = request.POST.get(
            'description',
            ''
        ).strip()

        if reason:

            ProjectReport.objects.create(
                project=project,
                reporter=request.user,
                reason=reason,
                description=description
            )

    return redirect(
        'blog:project_detail',
        pk=project.pk
    )


# =========================================================
# PROJECT SHARE
# =========================================================

@login_required
def project_share(request, pk):

    project = get_object_or_404(
        Project,
        pk=pk
    )

    platform = request.POST.get(
        'platform',
        'copy'
    )

    ProjectShare.objects.create(
        project=project,
        user=request.user,
        platform=platform
    )

    return redirect(
        'blog:project_detail',
        pk=project.pk
    )


# =========================================================
# COMMUNITY
# =========================================================

@login_required
def community(request):
    query = request.GET.get('q', '').strip()[:100]
    category = request.GET.get('category', '').strip()
    valid_categories = {choice[0] for choice in CommunityPost._meta.get_field('category').choices}

    posts = CommunityPost.objects.select_related(
        'author',
        'author__profile_data',
    ).annotate(
        like_count=Count('liked_by', distinct=True),
        reply_count=Count('replies', distinct=True),
    ).order_by('-created_at', '-pk')
    if query:
        posts = posts.filter(
            Q(title__icontains=query)
            | Q(content__icontains=query)
            | Q(category__icontains=query)
        )
    if category in valid_categories:
        posts = posts.filter(category=category)

    page = Paginator(posts, 15).get_page(request.GET.get('page'))
    post_ids = [post.pk for post in page.object_list]
    liked_post_ids = set(
        CommunityPost.objects.filter(
            pk__in=post_ids,
            liked_by=request.user,
        ).values_list('pk', flat=True)
    )
    saved_post_ids = set(
        CommunityPost.objects.filter(
            pk__in=post_ids,
            saved_by=request.user,
        ).values_list('pk', flat=True)
    )
    visible_photo_user_ids = _community_visible_photo_user_ids(
        (post.author for post in page.object_list),
        request.user,
    )
    return render(
        request,
        'blog/community.html',
        {
            'username': request.user.username,
            'display_name': (
                getattr(
                    getattr(request.user, 'profile_data', None),
                    'display_name',
                    ''
                )
                or request.user.get_full_name()
                or request.user.username
            ),
            'posts': page,
            'query': query,
            'selected_category': category if category in valid_categories else '',
            'categories': CommunityPost._meta.get_field('category').choices,
            'liked_post_ids': liked_post_ids,
            'saved_post_ids': saved_post_ids,
            'visible_photo_user_ids': visible_photo_user_ids,
        }
    )


@login_required
def community_post_create(request):
    if request.method == 'POST':
        form = CommunityPostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            return redirect('blog:community_post_detail', pk=post.pk)
    else:
        form = CommunityPostForm()

    return render(
        request,
        'blog/community_post_form.html',
        {'form': form, 'is_edit': False},
    )


@login_required
def community_post_detail(request, pk):
    post = get_object_or_404(
        CommunityPost.objects.select_related(
            'author',
            'author__profile_data',
        ).annotate(
            like_count=Count('liked_by', distinct=True),
        ),
        pk=pk,
    )
    replies = list(post.replies.select_related(
        'author',
        'author__profile_data',
    ))
    visible_photo_user_ids = _community_visible_photo_user_ids(
        [post.author, *(reply.author for reply in replies)],
        request.user,
    )
    return render(
        request,
        'blog/community_post_detail.html',
        {
            'post': post,
            'replies': replies,
            'is_liked': post.liked_by.filter(pk=request.user.pk).exists(),
            'is_saved': post.saved_by.filter(pk=request.user.pk).exists(),
            'visible_photo_user_ids': visible_photo_user_ids,
        },
    )


@login_required
def community_post_edit(request, pk):
    post = get_object_or_404(CommunityPost, pk=pk)
    if post.author_id != request.user.pk:
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = CommunityPostForm(request.POST, instance=post)
        if form.is_valid():
            form.save()
            return redirect('blog:community_post_detail', pk=post.pk)
    else:
        form = CommunityPostForm(instance=post)

    return render(
        request,
        'blog/community_post_form.html',
        {'form': form, 'post': post, 'is_edit': True},
    )


@login_required
@require_POST
def community_post_delete(request, pk):
    post = get_object_or_404(CommunityPost, pk=pk)
    if post.author_id != request.user.pk:
        return HttpResponseForbidden()
    post.delete()
    return redirect('blog:community')


@login_required
@require_POST
def community_reply_create(request, pk):
    post = get_object_or_404(CommunityPost, pk=pk)
    content = request.POST.get('content', '').strip()
    if not content:
        django_messages.error(request, 'Write a reply before submitting.')
    elif len(content) > 10000:
        django_messages.error(request, 'Replies must be 10,000 characters or fewer.')
    else:
        with transaction.atomic():
            CommunityReply.objects.create(
                post=post,
                author=request.user,
                content=content,
            )
            if post.author_id != request.user.pk:
                Notification.objects.create(
                    recipient=post.author,
                    sender=request.user,
                    notification_type='COMMUNITY_REPLY',
                    community_post=post,
                    message=(
                        f'{request.user.username[:60]} replied to your question: '
                        f'{post.title[:160]}'
                    ),
                )
        django_messages.success(request, 'Your reply was added.')
    return redirect('blog:community_post_detail', pk=post.pk)


@login_required
def community_reply_edit(request, pk):
    reply = get_object_or_404(
        CommunityReply.objects.select_related('post'),
        pk=pk,
    )
    if reply.author_id != request.user.pk:
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = CommunityReplyForm(request.POST, instance=reply)
        if form.is_valid():
            form.save()
            return redirect('blog:community_post_detail', pk=reply.post_id)
    else:
        form = CommunityReplyForm(instance=reply)

    return render(
        request,
        'blog/community_reply_edit.html',
        {'form': form, 'reply': reply},
    )


@login_required
@require_POST
def community_reply_delete(request, pk):
    reply = get_object_or_404(
        CommunityReply.objects.select_related('post'),
        pk=pk,
    )
    if reply.author_id != request.user.pk:
        return HttpResponseForbidden()
    post_id = reply.post_id
    reply.delete()
    return redirect('blog:community_post_detail', pk=post_id)


def _community_return_url(request, post):
    next_url = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse('blog:community_post_detail', kwargs={'pk': post.pk})


def _community_visible_photo_user_ids(users, viewer):
    unique_users = {user.pk: user for user in users}
    return {
        user.pk
        for user in unique_users.values()
        if getattr(user, 'profile_data', None)
        and user.profile_data.profile_picture
        and _can_view_user_content(user, viewer)
    }


@login_required
@require_POST
def community_post_like(request, pk):
    post = get_object_or_404(CommunityPost, pk=pk)
    if post.liked_by.filter(pk=request.user.pk).exists():
        post.liked_by.remove(request.user)
    else:
        post.liked_by.add(request.user)
    return redirect(_community_return_url(request, post))


@login_required
@require_POST
def community_post_save(request, pk):
    post = get_object_or_404(CommunityPost, pk=pk)
    if post.saved_by.filter(pk=request.user.pk).exists():
        post.saved_by.remove(request.user)
    else:
        post.saved_by.add(request.user)
    return redirect(_community_return_url(request, post))