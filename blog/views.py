import os
import secrets

from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from google import genai
from django.http import JsonResponse

from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Avg
from django.db.models import Q
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
)

from .forms import (
    PostForm,
    CommentForm,
    EmailSignupForm,
    ProjectForm,
)


# =========================================================
# COURSE / BLOG LIST
# =========================================================

def blog(request):

    search = request.GET.get('search', '').strip()
    category = request.GET.get('category', '').strip()

    posts = Post.objects.all().order_by('-created_at')

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

    recent_posts = Post.objects.all().order_by(
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
        pk=pk
    )

    comments = Comment.objects.filter(
        post=post
    ).order_by('-created_at')

    lessons = post.lessons.all()

    enrollment = Enrollment.objects.filter(
        student=request.user,
        course=post
    ).first()

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
    }

    return render(
        request,
        'blog/post_detail.html',
        context
    )


# =========================================================
# LESSON DETAIL
# =========================================================

def lesson_detail(request, pk):

    lesson = get_object_or_404(
        Lesson,
        pk=pk
    )

    context = {
        'lesson': lesson,
        'course': lesson.course,
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
# EMAIL LOGIN
# =========================================================

def login_view(request):

    if request.method == "POST":

        email = request.POST.get(
            "email",
            ""
        ).strip().lower()

        password = request.POST.get(
            "password",
            ""
        )

        try:

            user = User.objects.get(
                email__iexact=email
            )

            authenticated_user = authenticate(
                request,
                username=user.username,
                password=password
            )

            if authenticated_user is not None:

                login(
                    request,
                    authenticated_user
                )

                try:

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

            return render(
                request,
                "blog/login.html",
                {
                    "error": "Invalid email or password."
                }
            )

        except User.DoesNotExist:

            return render(
                request,
                "blog/login.html",
                {
                    "error": "Invalid email or password."
                }
            )

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

    context = {
        "profile_user": profile_user,
        "user_profile": user_profile,
        "posts": posts,
        "projects": projects,

        # Basic statistics
        "post_count": posts.count(),
        "project_count": projects.count(),

        # Temporary values until follower/like system is added
        "follower_count": 0,
        "profile_like_count": 0,

        # Current user's relationship
        "is_owner": request.user == profile_user,
    }

    return render(
        request,
        "blog/user_profile.html",
        context
    )

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

    return render(
        request,
        'blog/notifications.html'
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

    return render(
        request,
        'blog/practice.html',
        {
            'username': request.user.username
        }
    )


# =========================================================
# ASSIGNMENTS
# =========================================================

@login_required
def assignments(request):

    return render(
        request,
        'blog/assignments.html',
        {
            'username': request.user.username
        }
    )


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

    return render(
        request,
        'blog/community.html',
        {
            'username': request.user.username
        }
    )