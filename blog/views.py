import os
import secrets
import json
from datetime import timedelta

from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from google import genai
from django.http import JsonResponse, HttpResponseForbidden

from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Max
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse
from .models import MessageAttachment

from .gmail_service import send_gmail

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
    Conversation,
    Message,
    Assignment,
    AssignmentAudience,
    AssignmentAttempt,
    AssignmentSubmission,
    UserAssignmentProgress,
    LessonProgress,
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
)
from .services.course_progress import (
    can_access_lesson,
    mark_lesson_completed,
    refresh_enrollment_progress,
    refresh_progress_for_assignment,
    start_lesson,
)
from .services.code_execution import (
    CodeExecutionError,
    CodeRunnerUnavailable,
    run_code,
    runner_is_configured,
    supported_languages,
)
from .services.leaderboard import leaderboard_rows

from .forms import (
    PostForm,
    CommentForm,
    EmailSignupForm,
    ProjectForm,
)


# =========================================================
# COURSE / BLOG LIST uyhnyuyu
# =========================================================

def blog(request):

    search = request.GET.get('search', '').strip()
    category = request.GET.get('category', '').strip()

    posts = Post.objects.filter(status='PUBLISHED').order_by('-created_at')

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

    recent_posts = Post.objects.filter(status='PUBLISHED').order_by(
        '-created_at'
    )[:4]

    my_enrollments = Enrollment.objects.filter(
        student=request.user
    ).select_related('course')
    for enrollment in my_enrollments:
        refresh_enrollment_progress(request.user, enrollment.course)

    context = {
        'username': request.user.username,
        'recent_posts': recent_posts,
        'user_profile': profile,
        'my_enrollments': my_enrollments,
        'dashboard_practice_stats': _practice_stats_for_user(request.user),
        'owned_project_count': Project.objects.filter(owner=request.user).count(),
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

    for enrollment in enrollments:
        refresh_enrollment_progress(request.user, enrollment.course)

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

        if selected_goal in [
            "job",
            "skill",
            "projects",
            "interview"
        ]:

            profile.goal = selected_goal
            profile.save()

            return redirect("blog:dashboard")

    context = {
        "username": request.user.username,
        "user_profile": profile,
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
def post_detail(request, pk):

    post = get_object_or_404(
        Post,
        pk=pk,
        status='PUBLISHED',
    )

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
                pk=post.pk
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

                return redirect(
                    'blog:post_detail',
                    pk=post.pk
                )

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
def start_lesson_view(request, course_pk, lesson_pk):
    course = get_object_or_404(
        Post,
        pk=course_pk,
        status='PUBLISHED',
    )
    lesson = get_object_or_404(
        Lesson,
        pk=lesson_pk,
        course=course,
        course__status='PUBLISHED',
    )

    Enrollment.objects.get_or_create(
        student=request.user,
        course=course,
    )

    if not can_access_lesson(request.user, lesson):
        return HttpResponseForbidden('Complete the earlier lessons first.')

    start_lesson(request.user, lesson)
    return redirect('blog:lesson_detail', pk=lesson.pk)


def lesson_detail(request, pk):

    lesson = get_object_or_404(
        Lesson,
        pk=pk,
        course__status='PUBLISHED',
    )

    if not request.user.is_authenticated:
        return redirect('blog:login')

    enrolled = Enrollment.objects.filter(
        student=request.user,
        course=lesson.course
    ).exists()
    if not enrolled:
        return redirect('blog:post_detail', pk=lesson.course_id)
    if not can_access_lesson(request.user, lesson):
        return HttpResponseForbidden('Complete the earlier lessons first.')

    lesson_progress = start_lesson(request.user, lesson)
    ordered_lessons = list(lesson.course.lessons.all())
    lesson_index = next(index for index, item in enumerate(ordered_lessons) if item.pk == lesson.pk)

    assignments = Assignment.objects.filter(
        assignment_source='COURSE',
        status='PUBLISHED',
        lesson=lesson
    ).filter(
        Q(release_date__isnull=True) | Q(release_date__lte=timezone.now())
    )

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
        'lesson_progress': lesson_progress,
        'previous_lesson': ordered_lessons[lesson_index - 1] if lesson_index else None,
        'next_lesson': ordered_lessons[lesson_index + 1] if lesson_index + 1 < len(ordered_lessons) else None,
    }

    return render(
        request,
        'blog/lesson_detail.html',
        context
    )


@login_required
def complete_lesson(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden('POST required.')

    lesson = get_object_or_404(Lesson.objects.select_related('course'), pk=pk)
    if not can_access_lesson(request.user, lesson):
        return HttpResponseForbidden('You must join this course first.')

    mark_lesson_completed(request.user, lesson)
    return redirect('blog:lesson_detail', pk=lesson.pk)


# =========================================================
# CREATE COURSE / POST
# =========================================================

@user_passes_test(lambda user: user.is_staff)
def create_post(request):

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

@user_passes_test(lambda user: user.is_staff)
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

@user_passes_test(lambda user: user.is_staff)
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

        form = EmailSignupForm(request.POST)

        if form.is_valid():

            user = form.save()

            try:

                send_gmail(
                    user.email,
                    "CodeLearn Hub - Account Created Successfully",
                    f"""Hi,

Your CodeLearn Hub account has been created successfully.

You can now log in and start learning.

Welcome to CodeLearn Hub!

Regards,
CodeLearn Hub Team
"""
                )

            except Exception as error:

                print(
                    "Registration email failed:",
                    error
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

            request.session["reset_email"] = user.email
            request.session["reset_otp"] = otp
            request.session["otp_verified"] = False

            send_gmail(
                user.email,
                "CodeLearn Hub - Password Reset OTP",
                f"""Hi,

We received a request to reset your CodeLearn Hub password.

Your password reset OTP is:

{otp}

Use this OTP to verify your identity and reset your password.

If you did not request a password reset, you can safely ignore this email.

Regards,
CodeLearn Hub Team
"""
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

        except Exception as error:

            print(
                "Forgot password email failed:",
                error
            )

            return render(
                request,
                "blog/login.html",
                {
                    "show_forgot": True,
                    "error": "Unable to send OTP. Please try again."
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
# USERNAME / EMAIL LOGIN
# =========================================================

def login_view(request):

    if request.method == "POST":

        identifier = request.POST.get(
            "username",
            ""
        ).strip()

        password = request.POST.get(
            "password",
            ""
        )

        # -------------------------------------------------
        # EMPTY FIELD CHECK
        # -------------------------------------------------

        if not identifier or not password:

            return render(
                request,
                "blog/login.html",
                {
                    "error":
                        "Please enter username/email and password."
                }
            )

        # -------------------------------------------------
        # FIND USERS BY USERNAME OR EMAIL
        # -------------------------------------------------

        users = User.objects.filter(
            Q(username__iexact=identifier) |
            Q(email__iexact=identifier)
        )

        authenticated_user = None

        # -------------------------------------------------
        # CHECK PASSWORD
        # -------------------------------------------------

        for user in users:

            authenticated_user = authenticate(
                request,
                username=user.username,
                password=password
            )

            if authenticated_user is not None:
                break

        # -------------------------------------------------
        # LOGIN SUCCESS
        # -------------------------------------------------

        if authenticated_user is not None:

            login(
                request,
                authenticated_user
            )

            # Send login email if available.
            # Email failure should NOT stop login.

            try:

                if authenticated_user.email:

                    send_gmail(
                        authenticated_user.email,
                        "CodeLearn Hub - Login Successful",
                        """Hi,

You have successfully logged in to your CodeLearn Hub account.

If this was not you, please secure your account immediately.

Regards,
CodeLearn Hub Team
"""
                    )

            except Exception as error:

                print(
                    "Login email failed:",
                    error
                )

            return redirect(
                "blog:dashboard"
            )

        # -------------------------------------------------
        # LOGIN FAILED
        # -------------------------------------------------

        return render(
            request,
            "blog/login.html",
            {
                "error":
                    "Invalid username/email or password."
            }
        )

    # -----------------------------------------------------
    # GET REQUEST
    # -----------------------------------------------------

    return render(
        request,
        "blog/login.html"
    )
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

        post_pk = comment.post.pk

        comment.delete()

        return redirect(
            'blog:post_detail',
            pk=post_pk
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
                pk=comment.post.pk
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

    posts = Post.objects.filter(
        author=request.user
    ).order_by('-created_at')

    projects = Project.objects.filter(
        owner=request.user
    ).order_by('-created_at')

    profile, created = UserProfile.objects.get_or_create(
        user=request.user
    )

    context = {
        'posts': posts,
        'projects': projects,
        'username': request.user.username,
        'user_profile': profile,
    }

    return render(
        request,
        'blog/profile.html',
        context
    )

# =========================================================
# USER PROFILE
# =========================================================

@login_required
def user_profile(request, user_id):

    profile_user = get_object_or_404(
        User,
        id=user_id
    )

    posts = Post.objects.filter(
        author=profile_user
    ).order_by("-created_at")

    projects = Project.objects.filter(
        owner=profile_user
    ).order_by("-created_at")

    user_profile, created = UserProfile.objects.get_or_create(
        user=profile_user
    )

    # Followers
    follower_count = FollowRequest.objects.filter(
        receiver=profile_user,
        status="ACCEPTED"
    ).count()

    # Following
    following_count = FollowRequest.objects.filter(
        sender=profile_user,
        status="ACCEPTED"
    ).count()

    is_owner = request.user == profile_user

    # Current user's relationship with this profile
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

    incoming_request = FollowRequest.objects.filter(
            sender=profile_user,
            receiver=request.user,
            status="PENDING"
    ).first()

    incoming_pending = incoming_request is not None 

# incoming_pending = incoming_request is not None

    context = {

        "profile_user": profile_user,

        "user_profile": user_profile,

        "posts": posts,

        "projects": projects,

        "post_count": posts.count(),

        "project_count": projects.count(),

        "follower_count": follower_count,

        "following_count": following_count,

        "is_owner": is_owner,

        "is_following": is_following,

        "outgoing_pending": outgoing_pending,

        "incoming_pending": incoming_pending,

        "incoming_request_id": (
            incoming_request.id
            if incoming_request
            else None
),
    }

    return render(
        request,
        "blog/user_profile.html",
        context
    )
# =========================================================
# USER FOLLOW SYSTEM
# =========================================================

@login_required
def send_follow_request(request, user_id):

    if request.method != "POST":
        return JsonResponse({
            "success": False,
            "error": "Invalid request."
        }, status=400)

    receiver = get_object_or_404(
        User,
        id=user_id
    )

    # Cannot follow yourself
    if request.user == receiver:
        return JsonResponse({
            "success": False,
            "error": "You cannot follow yourself."
        }, status=400)

    existing_request = FollowRequest.objects.filter(
        sender=request.user,
        receiver=receiver
    ).first()

    # Already accepted
    if existing_request and existing_request.status == "ACCEPTED":
        return JsonResponse({
            "success": False,
            "error": "You are already following this user."
        }, status=400)

    # Existing pending request
    if existing_request and existing_request.status == "PENDING":
        return JsonResponse({
            "success": False,
            "error": "Follow request already pending."
        }, status=400)

    # Re-use rejected request
    if existing_request and existing_request.status == "REJECTED":

        existing_request.status = "PENDING"
        existing_request.save(
            update_fields=["status", "updated_at"]
        )

        is_follow_back = FollowRequest.objects.filter(
            sender=receiver,
            receiver=request.user,
            status="ACCEPTED"
        ).exists()

        notification_type = (
            "FOLLOW_BACK"
            if is_follow_back
            else "FOLLOW_REQUEST"
        )

        notification_message = (
            f"@{request.user.username} wants to follow you back."
            if is_follow_back
            else f"@{request.user.username} sent you a follow request."
        )

        Notification.objects.create(
            recipient=receiver,
            sender=request.user,
            notification_type=notification_type,
            message=notification_message
        )

        return JsonResponse({
            "success": True,
            "status": "PENDING",
            "message": "Follow request sent."
        })

    # Check if receiver already follows sender
    is_follow_back = FollowRequest.objects.filter(
        sender=receiver,
        receiver=request.user,
        status="ACCEPTED"
    ).exists()

    follow_request = FollowRequest.objects.create(
        sender=request.user,
        receiver=receiver,
        status="PENDING"
    )

    notification_type = (
        "FOLLOW_BACK"
        if is_follow_back
        else "FOLLOW_REQUEST"
    )

    notification_message = (
        f"@{request.user.username} wants to follow you back."
        if is_follow_back
        else f"@{request.user.username} sent you a follow request."
    )

    Notification.objects.create(
        recipient=receiver,
        sender=request.user,
        notification_type=notification_type,
        message=notification_message
    )

    return JsonResponse({
        "success": True,
        "status": "PENDING",
        "request_id": follow_request.id,
        "message": "Follow request sent."
    })


# cancle flow

@login_required
def cancel_follow_request(request, user_id):

    if request.method != "POST":
        return JsonResponse({
            "success": False,
            "error": "Invalid request."
        }, status=400)

    receiver = get_object_or_404(
        User,
        id=user_id
    )

    follow_request = FollowRequest.objects.filter(
        sender=request.user,
        receiver=receiver,
        status="PENDING"
    ).first()

    if not follow_request:
        return JsonResponse({
            "success": False,
            "error": "No pending follow request found."
        }, status=404)

    follow_request.delete()

    return JsonResponse({
        "success": True,
        "status": "NONE",
        "message": "Follow request cancelled."
    })

# accept follow reqest
@login_required
def accept_follow_request(request, request_id):

    if request.method != "POST":
        return JsonResponse({
            "success": False,
            "error": "Invalid request."
        }, status=400)

    follow_request = get_object_or_404(
        FollowRequest,
        id=request_id,
        receiver=request.user,
        status="PENDING"
    )

    follow_request.status = "ACCEPTED"

    follow_request.save(
        update_fields=["status", "updated_at"]
    )

    Notification.objects.create(
        recipient=follow_request.sender,
        sender=request.user,
        notification_type="FOLLOW_ACCEPTED",
        message=(
            f"@{request.user.username} accepted your "
            f"follow request."
        )
    )

    conversation = Conversation.objects.filter(
        project__isnull=True
    ).filter(
        Q(
            project_owner=request.user,
            participant=follow_request.sender
        ) |
        Q(
            project_owner=follow_request.sender,
            participant=request.user
        )
    ).first()

    if conversation is None:
        conversation = Conversation.objects.create(
            project=None,
            project_owner=request.user,
            participant=follow_request.sender
        )

    return JsonResponse({
        "success": True,
        "status": "ACCEPTED",
        "conversation_id": conversation.id,
        "redirect_url": reverse(
            "blog:conversation_detail",
            args=[conversation.id]
        ),
        "message": "Follow request accepted."
    })
# Reject Follow Request
@login_required
def reject_follow_request(request, request_id):

    if request.method != "POST":
        return JsonResponse({
            "success": False,
            "error": "Invalid request."
        }, status=400)

    follow_request = get_object_or_404(
        FollowRequest,
        id=request_id,
        receiver=request.user,
        status="PENDING"
    )

    sender = follow_request.sender

    follow_request.status = "REJECTED"

    follow_request.save(
        update_fields=["status", "updated_at"]
    )

    Notification.objects.create(
        recipient=sender,
        sender=request.user,
        notification_type="FOLLOW_REJECTED",
        message=(
            f"@{request.user.username} declined "
            f"your follow request."
        )
    )

    return JsonResponse({
        "success": True,
        "status": "REJECTED",
        "message": "Follow request rejected."
    })

# Unfollow

@login_required
def unfollow_user(request, user_id):

    if request.method != "POST":
        return JsonResponse({
            "success": False,
            "error": "Invalid request."
        }, status=400)

    target_user = get_object_or_404(
        User,
        id=user_id
    )

    if request.user == target_user:
        return JsonResponse({
            "success": False,
            "error": "You cannot unfollow yourself."
        }, status=400)

    follow_request = FollowRequest.objects.filter(
        sender=request.user,
        receiver=target_user,
        status="ACCEPTED"
    ).first()

    if not follow_request:
        return JsonResponse({
            "success": False,
            "error": "You are not following this user."
        }, status=400)

    follow_request.delete()

    return JsonResponse({
        "success": True,
        "status": "NONE",
        "message": "User unfollowed."
    })
# =========================================================
# PERSONAL CHAT CONNECT
# =========================================================


@login_required
def start_personal_chat(request, user_id):

    if request.method != "POST":

        return JsonResponse({
            "success": False,
            "error": "Invalid request."
        }, status=400)

    profile_user = get_object_or_404(
        User,
        id=user_id
    )

    if request.user == profile_user:

        return JsonResponse({
            "success": False,
            "error": "You cannot connect with yourself."
        }, status=400)

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
def settings_view(request):

    return render(
        request,
        'blog/settings.html'
    )


# =========================================================
# NOTIFICATIONS
# =========================================================

@login_required
def notifications(request):

    notifications = Notification.objects.filter(
        recipient=request.user
    ).select_related(
        'sender'
    ).order_by('-created_at')

    if request.method == 'POST' and request.POST.get('mark_all_read') == '1':
        notifications.filter(is_read=False).update(is_read=True)
        return redirect('blog:notifications')

    return render(
        request,
        'blog/notifications.html',
        {
            'notifications': notifications,
            'unread_count': notifications.filter(is_read=False).count(),
            'username': request.user.username,
        }
    )


# =========================================================
# AI TUTOR
# =========================================================

@login_required
def ai_tutor(request):

    answer = None
    question = ""
    error = None

    if request.method == "POST":

        question = request.POST.get(
            "question",
            ""
        ).strip()

        if question:

            try:

                client = genai.Client(
                    api_key=os.getenv(
                        "GEMINI_API_KEY"
                    )
                )

                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=(
                        f"You are {settings.SITE_NAME} AI Tutor. "
                        "Help students learn programming step by step. "
                        "Give clear, beginner-friendly explanations.\n\n"
                        f"Student question: {question}"
                    ),
                )

                answer = response.text

            except Exception as e:

                print(
                    "AI Tutor Error:",
                    e
                )

                error = (
                    "AI Tutor is temporarily busy. "
                    "Please try again in a few seconds."
                )

    return render(
        request,
        "blog/ai_tutor.html",
        {
            "question": question,
            "answer": answer,
            "error": error,
        },
    )


# =========================================================
# PRACTICE
# =========================================================

@login_required
def practice(request):

    stats = _practice_stats_for_user(request.user)
    problems = PracticeProblem.objects.filter(active=True).order_by('id')
    problem_rows = [
        {
            'problem': problem,
            'status': stats['user_progress'].get(problem.id, 'NOT_ATTEMPTED'),
        }
        for problem in problems
    ]
    database_problems = [
        {
            'slug': problem.slug,
            'title': problem.title,
            'description': problem.description,
            'difficulty': problem.difficulty,
            'category': problem.category,
            'tags': problem.tags,
            'function_name': problem.function_name,
            'starter_code': problem.starter_code,
            'example': problem.example,
            'constraints': problem.constraints,
            'public_tests': problem.public_tests,
            'hidden_tests': problem.hidden_tests,
        }
        for problem in problems
    ]
    progress_state = {
        item.problem.slug: {
            'status': item.status,
            'attemptCount': item.attempt_count,
            'lastSubmissionId': item.last_submission_id,
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
            'submittedAt': int(item.submitted_at.timestamp() * 1000),
        }
        for item in PracticeSubmission.objects.filter(user=request.user).select_related('problem')[:100]
    ]

    return render(
        request,
        'blog/practice.html',
        {
            'username': request.user.username,
            'problems': problem_rows,
            'database_problems': database_problems,
            'practice_stats': stats,
            'practice_state': json.dumps({'progress': progress_state, 'submissions': submissions}),
        }
    )


def _practice_problem(slug):
    problem = PracticeProblem.objects.filter(slug=slug, active=True).first()
    if problem:
        return problem

    bundled_slugs = {
        'two-sum', 'reverse-a-string', 'palindrome-check', 'fizzbuzz',
        'valid-parentheses', 'merge-two-sorted-lists', 'longest-substring', 'valid-bst',
    }
    if slug not in bundled_slugs:
        return get_object_or_404(PracticeProblem, slug=slug, active=True)

    function_name = slug.replace('-', '_')
    return PracticeProblem.objects.get_or_create(
        slug=slug,
        defaults={
            'title': slug.replace('-', ' ').title(),
            'description': 'Bundled coding practice problem.',
            'difficulty': 'EASY',
            'category': 'python',
            'function_name': function_name,
            'starter_code': {
                'python': f'def {function_name}():\n    pass\n',
                'javascript': f'function {function_name}() {{\n}}\n',
                'java': '',
            },
            'public_tests': [],
            'hidden_tests': [],
        },
    )[0]


def _practice_stats_for_user(user):
    problem_count = PracticeProblem.objects.filter(active=True).count()
    user_progress = {
        item.problem_id: item.status
        for item in PracticeProgress.objects.filter(user=user).select_related('problem')
    }
    solved = sum(1 for value in user_progress.values() if value == 'SOLVED')
    attempted = sum(1 for value in user_progress.values() if value == 'ATTEMPTED')
    pending = max(problem_count - solved - attempted, 0)

    completed_tests = MockTestAttempt.objects.filter(
        user=user,
        status__in=('COMPLETED', 'EXPIRED'),
    )
    test_scores = list(completed_tests.values_list('score', 'total_score'))
    score_percentages = [round(score * 100 / total, 1) for score, total in test_scores if total]
    average_test_score = round(sum(score_percentages) / len(score_percentages), 1) if score_percentages else 0
    best_test_score = max(score_percentages, default=0)
    solved_difficulty = {
        row['problem__difficulty'].lower(): row['total']
        for row in PracticeProgress.objects.filter(user=user, status='SOLVED')
        .values('problem__difficulty')
        .annotate(total=Count('id'))
    }
    activity_days = set(
        PracticeSubmission.objects.filter(user=user).dates('submitted_at', 'day', order='DESC')
    )
    activity_days.update(
        completed_tests.exclude(submitted_at__isnull=True).dates('submitted_at', 'day', order='DESC')
    )
    today = timezone.localdate()
    streak = 0
    streak_day = today if today in activity_days else today - timedelta(days=1)
    while streak_day in activity_days:
        streak += 1
        streak_day -= timedelta(days=1)

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
    recent_activity.sort(key=lambda activity: activity['created_at'], reverse=True)

    return {
        'total_problems': problem_count,
        'solved': solved,
        'attempted': attempted,
        'pending': pending,
        'accuracy': round((solved / problem_count) * 100, 1) if problem_count else 0,
        'mock_tests_completed': completed_tests.count(),
        'average_mock_score': average_test_score,
        'best_mock_score': best_test_score,
        'easy_solved': solved_difficulty.get('easy', 0),
        'medium_solved': solved_difficulty.get('medium', 0),
        'hard_solved': solved_difficulty.get('hard', 0),
        'mock_test_minutes': round(sum(
            max(0, (attempt.submitted_at - attempt.started_at).total_seconds()) / 60
            for attempt in completed_tests.exclude(submitted_at__isnull=True)
        )),
        'streak': streak,
        'recent_activity': recent_activity[:5],
        'user_progress': user_progress,
    }


@login_required
def practice_details(request):
    stats = _practice_stats_for_user(request.user)
    return render(
        request,
        'blog/practice_details.html',
        {
            'username': request.user.username,
            'stats': stats,
            'recent_activity': stats['recent_activity'],
        },
    )


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
    problem_rows = []
    for problem in problems:
        status = stats['user_progress'].get(problem.id, 'NOT_ATTEMPTED')
        if status_filter and status_filter != status:
            continue
        problem_rows.append({
            'problem': problem,
            'status': status,
        })
    categories = PracticeProblem.objects.filter(active=True).values_list('category', flat=True).distinct()
    problem_page = Paginator(problem_rows, 20).get_page(request.GET.get('page'))
    return render(
        request,
        'blog/practice_all.html',
        {
            'username': request.user.username,
            'problems': problem_page,
            'stats': stats,
            'progress_map': stats['user_progress'],
            'search': search,
            'selected_category': category,
            'selected_difficulty': difficulty,
            'selected_status': status_filter,
            'categories': categories,
        },
    )


@login_required
def practice_playground(request):
    session = None
    session_id = request.GET.get('session')
    if session_id:
        session = get_object_or_404(PlaygroundSession, pk=session_id, user=request.user)
    languages = supported_languages() if runner_is_configured() else ()
    return render(
        request,
        'blog/practice_playground.html',
        {
            'username': request.user.username,
            'session': session,
            'languages': languages,
            'selected_language': session.language if session else (languages[0] if languages else ''),
            'sessions': PlaygroundSession.objects.filter(user=request.user)[:10],
            'runner_configured': runner_is_configured(),
        },
    )


@login_required
def practice_mock_tests(request):
    tests = MockTest.objects.filter(active=True).annotate(question_count=Count('questions'))
    attempts = MockTestAttempt.objects.filter(user=request.user).select_related('test')
    latest_by_test = {}
    for attempt in attempts:
        latest_by_test.setdefault(attempt.test_id, attempt)
    test_rows = [
        {'test': mock_test, 'attempt': latest_by_test.get(mock_test.id)}
        for mock_test in tests
    ]
    return render(
        request,
        'blog/practice_mock_tests.html',
        {
            'username': request.user.username,
            'tests': test_rows,
            'stats': _practice_stats_for_user(request.user),
        },
    )


@login_required
def practice_problem_sets(request):
    sets = PracticeProblemSet.objects.filter(active=True).prefetch_related('problems')
    set_rows = []
    for problem_set in sets:
        set_problems = problem_set.problems.filter(active=True)
        problem_ids = list(set_problems.values_list('id', flat=True))
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

    return render(
        request,
        'blog/practice_problem_sets.html',
        {
            'username': request.user.username,
            'sets': set_rows,
            'stats': _practice_stats_for_user(request.user),
        },
    )


@login_required
def practice_leaderboard(request):
    period = request.GET.get('period', 'all').lower()
    leaderboard, period = leaderboard_rows(period)
    current_rank = next(
        (rank for rank, row in enumerate(leaderboard, start=1) if row['user'].id == request.user.id),
        None,
    )
    leaderboard_page = Paginator(leaderboard, 25).get_page(request.GET.get('page'))

    return render(
        request,
        'blog/practice_leaderboard.html',
        {
            'username': request.user.username,
            'leaderboard': leaderboard_page,
            'podium': leaderboard[:3],
            'period': period,
            'current_rank': current_rank,
            'stats': _practice_stats_for_user(request.user),
        },
    )


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

    session_id = payload.get('sessionId')
    session = None
    if session_id:
        session = get_object_or_404(PlaygroundSession, pk=session_id, user=request.user)
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
        'languages': [item for item in supported_languages() if item in (problem.starter_code or {})] if runner_is_configured() else [],
    })


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
    visible_cases = problem.public_tests or []
    hidden_cases = problem.hidden_tests or [] if submit else []
    if any(not isinstance(test_case, dict) for test_case in visible_cases + hidden_cases):
        return JsonResponse({'error': 'This problem has invalid test configuration.'}, status=409)
    cases = [dict(test_case, hidden=False) for test_case in visible_cases]
    cases.extend(dict(test_case, hidden=True) for test_case in hidden_cases)
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
    passed = sum(1 for test_result in test_results if test_result['passed'])
    is_accepted = submit and result['status'] in ('SUCCESS', 'ACCEPTED') and len(test_results) == len(cases) and passed == len(cases)
    status = 'ACCEPTED' if is_accepted else result['status']
    if submit and not is_accepted and status in ('SUCCESS', 'ACCEPTED'):
        status = 'WRONG_ANSWER'

    with transaction.atomic():
        progress, _ = PracticeProgress.objects.select_for_update().get_or_create(
            user=request.user,
            problem=problem,
        )
        progress.attempt_count += 1
        progress.last_attempt_at = timezone.now()
        if is_accepted:
            progress.status = 'SOLVED'
            progress.solved_at = progress.solved_at or timezone.now()
        elif progress.status != 'SOLVED':
            progress.status = 'ATTEMPTED'
        progress.save()

        submission = None
        if submit:
            visible_results = [item for item in test_results if not item.get('hidden')]
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
                    'visible_test_results': visible_results,
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
        'solved_count': sum(1 for row in rows if row['status'] == 'SOLVED'),
    })


@login_required
def practice_mock_test_detail(request, pk):
    mock_test = get_object_or_404(MockTest, pk=pk, active=True)
    questions = mock_test.questions.all()
    question_count = questions.count()
    total_points = sum(questions.values_list('points', flat=True))
    attempts = MockTestAttempt.objects.filter(user=request.user, test=mock_test)
    latest_attempt = attempts.first()
    return render(request, 'blog/practice_mock_test_detail.html', {
        'mock_test': mock_test,
        'question_count': question_count,
        'total_points': total_points,
        'latest_attempt': latest_attempt,
        'can_start': bool(question_count) and (mock_test.allow_retakes or not attempts.filter(status__in=('COMPLETED', 'EXPIRED')).exists()),
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
    if not mock_test.allow_retakes and attempts.filter(status__in=('COMPLETED', 'EXPIRED')).exists():
        latest = attempts.filter(status__in=('COMPLETED', 'EXPIRED')).first()
        return redirect('blog:practice_mock_test_result', pk=latest.pk)
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
    total_score = sum(question.points for question in questions)
    score = 0
    for question in questions:
        answer = attempt.answers.get(str(question.id))
        if answer is not None and str(answer) == str(question.correct_answer):
            score += question.points
    attempt.score = score
    attempt.total_score = total_score
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
        {
            'question': question,
            'answer': attempt.answers.get(str(question.id), ''),
        }
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
        question = get_object_or_404(MockTestQuestion, pk=payload.get('questionId'), test=attempt.test)
        answer = str(payload.get('answer', ''))[:500]
        option_ids = {str(option.get('id', '')) for option in question.options if isinstance(option, dict)}
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
        correct_option = next(
            (option for option in question.options if isinstance(option, dict) and str(option.get('id')) == str(question.correct_answer)),
            None,
        )
        selected_option = next(
            (option for option in question.options if isinstance(option, dict) and str(option.get('id')) == str(answer)),
            None,
        )
        question_rows.append({
            'question': question,
            'answer': answer,
            'correct': correct,
            'selected_option': selected_option,
            'correct_option': correct_option,
        })
    elapsed_seconds = max(0, int(((attempt.submitted_at or timezone.now()) - attempt.started_at).total_seconds()))
    answered_count = sum(1 for row in question_rows if row['answer'] is not None)
    correct_count = sum(1 for row in question_rows if row['correct'])
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
    payload = _practice_json_payload(request)
    if payload is None:
        return JsonResponse({'error': 'Invalid or oversized request.'}, status=400)
    problem = _practice_problem(str(payload.get('problemId', '')))
    language = str(payload.get('language', '')).strip().lower()
    source_code = payload.get('sourceCode', '')
    if language not in {'python', 'javascript', 'java'} or not isinstance(source_code, str):
        return JsonResponse({'error': 'Invalid language or source code.'}, status=400)
    if len(source_code.encode('utf-8')) > 20_000:
        return JsonResponse({'error': 'Code is larger than the allowed limit.'}, status=400)
    progress, _ = PracticeProgress.objects.get_or_create(
        user=request.user,
        problem=problem,
    )
    drafts = progress.code_drafts or {}
    drafts[language] = source_code
    progress.code_drafts = drafts
    progress.save(update_fields=['code_drafts'])
    return JsonResponse({'saved': True})


@login_required
def practice_record(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    payload = _practice_json_payload(request)
    if payload is None:
        return JsonResponse({'error': 'Invalid or oversized request.'}, status=400)
    kind = payload.get('kind')
    if kind not in {'run', 'submit'}:
        return JsonResponse({'error': 'Invalid practice action.'}, status=400)

    problem = _practice_problem(str(payload.get('problemId', '')))
    language = str(payload.get('language', '')).strip().lower()
    source_code = payload.get('sourceCode', '')
    if language not in {'python', 'javascript', 'java'}:
        return JsonResponse({'error': 'Unsupported language.'}, status=400)
    if not isinstance(source_code, str) or len(source_code.encode('utf-8')) > 20_000:
        return JsonResponse({'error': 'Code is larger than the allowed limit.'}, status=400)

    allowed_statuses = {choice[0] for choice in PracticeSubmission.STATUS_CHOICES}
    status = str(payload.get('status', 'INTERNAL_ERROR')).upper()
    if status not in allowed_statuses:
        status = 'INTERNAL_ERROR'
    try:
        passed = min(max(int(payload.get('passed') or 0), 0), 100)
        total = min(max(int(payload.get('total') or 0), 0), 100)
        runtime = max(int(payload['runtime']), 0) if payload.get('runtime') is not None else None
    except (TypeError, ValueError, OverflowError):
        return JsonResponse({'error': 'Invalid result data.'}, status=400)

    with transaction.atomic():
        progress, _ = PracticeProgress.objects.select_for_update().get_or_create(
            user=request.user,
            problem=problem,
        )
        progress.attempt_count += 1
        progress.last_attempt_at = timezone.now()
        if kind == 'submit' and status == 'ACCEPTED':
            progress.status = 'SOLVED'
            progress.solved_at = progress.solved_at or timezone.now()
        elif progress.status != 'SOLVED':
            progress.status = 'ATTEMPTED'
        progress.save()

        submission = None
        if kind == 'submit':
            submission = PracticeSubmission.objects.create(
                user=request.user,
                problem=problem,
                language=language,
                source_code=source_code,
                status=status,
                passed_test_cases=passed,
                total_test_cases=total,
                execution_time=runtime,
                memory_used=payload.get('memory'),
                result_data={'status': status, 'passed': passed, 'total': total},
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

    summary_progress = {
        item.assignment_id: item
        for item in UserAssignmentProgress.objects.filter(
            user=request.user,
            assignment__in=assignments_qs,
        )
    }
    summary_items = list(assignments_qs)
    summary_completed = [
        item for item in summary_items
        if summary_progress.get(item.id) and summary_progress[item.id].status in ('EVALUATED', 'PASSED')
    ]
    scored_items = [
        summary_progress[item.id]
        for item in summary_items
        if item.id in summary_progress and summary_progress[item.id].best_score is not None
    ]
    completion_percent = round(len(summary_completed) * 100 / len(summary_items)) if summary_items else 0
    average_score = round(sum(
        progress.best_score * 100 / progress.assignment.max_score
        for progress in scored_items
        if progress.assignment.max_score
    ) / len(scored_items)) if scored_items else 0

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
            'completion_percent': completion_percent,
            'remaining_to_80': max(0, round((80 * len(summary_items) / 100) - len(summary_completed))) if summary_items else 0,
            'average_score': average_score,
            'upcoming_assignments': [
                item for item in summary_items
                if item.due_date and item.due_date >= timezone.now()
            ][:3],
        }
    )


@login_required
def assignment_attempt(request, pk):
    assignment = get_object_or_404(Assignment.objects.select_related('course', 'lesson__course'), pk=pk)
    if not _can_access_assignment(request.user, assignment):
        return HttpResponseForbidden('You do not have access to this assignment.')
    if assignment.lesson and not can_access_lesson(request.user, assignment.lesson):
        return HttpResponseForbidden('Complete the earlier lessons first.')

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

    questions = assignment.questions.select_related('assignment').prefetch_related('options').order_by('order', 'id')

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
                submission.file = uploaded_file
                answer_data['file_name'] = uploaded_file.name
                attempt.answer_data = answer_data
            submission.save()
        progress.submitted_at = timezone.now()
        progress.save()
        attempt.save()
        refresh_progress_for_assignment(request.user, assignment)
        return redirect('blog:assignment_attempt', pk=assignment.pk)

    return render(request, 'blog/assignment_attempt.html', {
        'assignment': assignment,
        'attempt': attempt,
        'questions': questions,
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
        "project_owner",
        "participant"
    ).prefetch_related(
        "messages__sender"
    ).order_by(
        "-updated_at"
    )

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

    available_users = User.objects.exclude(
        id=request.user.id
    ).order_by(
        "username"
    )

    return render(
        request,
        "blog/messages.html",
        {
            "conversations": conversations,
            "available_users": available_users,
        }
    )


# @login_required
@login_required
def conversation_detail(request, conversation_id):

    conversation = get_object_or_404(
        Conversation.objects.select_related(
            "project",
            "project_owner",
            "participant"
        ).prefetch_related(
            "messages__sender",
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
    "sender"
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

    messages = conversation.messages.exclude(
    deleted_for_users=request.user
        ).values(
            "id",
            "sender_id",
            "content",
            "is_delivered",
            "is_read",
            "deleted_for_everyone"
)

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

    projects = Project.objects.select_related(
        'owner'
    ).prefetch_related(
        'likes',
        'comments',
    ).order_by('-created_at')[:12]

    for project in projects:
        project.like_count = project.likes.count()
        project.comment_count = project.comments.count()

    context = {
        'username': request.user.username,
        'projects': projects,
        'member_count': User.objects.count(),
        'project_count': Project.objects.count(),
        'active_today': User.objects.filter(
            last_login__isnull=False
        ).count(),
    }

    return render(
        request,
        'blog/community.html',
        context
    )