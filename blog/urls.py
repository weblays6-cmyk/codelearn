from django.urls import path
from . import views
from django.contrib.auth import views as auth_views


app_name = "blog"


urlpatterns = [

    # =========================================================
    # HOME / COURSES
    # =========================================================

    path(
        "",
        views.blog,
        name="blogpage"
    ),

    path(
        "courses/",
        views.blog,
        name="blogpage"
    ),

    path(
        "course/<int:pk>/",
        views.post_detail,
        name="post_detail"
    ),

    path(
        "lesson/<int:pk>/",
        views.lesson_detail,
        name="lesson_detail"
    ),

    # =========================================================
    # DASHBOARD
    # =========================================================

    path(
        "dashboard/",
        views.dashboard,
        name="dashboard"
    ),

    path(
        "my-learning/",
        views.my_learning,
        name="my_learning"
    ),

    path(
        "goal/",
        views.choose_goal,
        name="choose_goal"
    ),

    # =========================================================
    # COURSE / POST MANAGEMENT
    # =========================================================

    path(
        "create-post/",
        views.create_post,
        name="create_post"
    ),

    path(
        "post/<int:pk>/update/",
        views.update_post,
        name="update_post"
    ),

    path(
        "post/<int:pk>/delete/",
        views.delete_post,
        name="delete_post"
    ),

    # =========================================================
    # COMMENTS
    # =========================================================

    path(
        "comment/<int:pk>/delete/",
        views.delete_comment,
        name="delete_comment"
    ),

    path(
        "comment/<int:pk>/update/",
        views.update_comment,
        name="update_comment"
    ),

    # =========================================================
    # AUTHENTICATION
    # =========================================================

    path(
        "signup/",
        views.signup,
        name="signup"
    ),

    path(
        "login/",
        views.login_view,
        name="login"
    ),

    path(
        "logout/", 
        auth_views.LogoutView.as_view(),
        name="logout"),

    path(
        "forgot-password/",
        views.forgot_password,
        name="forgot_password"
    ),

    path(
        "verify-otp/",
        views.verify_otp,
        name="verify_otp"
    ),

    path(
        "reset-password/",
        views.reset_password,
        name="reset_password"
    ),

    # =========================================================
    # PROFILE / ACCOUNT
    # =========================================================

    path(
        "profile/",
        views.profile,
        name="profile"
    ),

    path(
    "profile/<int:user_id>/",
    views.user_profile,
    name="user_profile"
    ),  

    path(
    "profile/<int:user_id>/connect/",
    views.start_personal_chat,
    name="start_personal_chat"
    ),

    path(
        "settings/",
        views.settings_view,
        name="settings"
    ),

    path(
        "notifications/",
        views.notifications,
        name="notifications"
    ),

    # =========================================================
    # AI TUTOR
    # =========================================================

    path(
        "ai-tutor/",
        views.ai_tutor,
        name="ai_tutor"
    ),

    # =========================================================
    # PRACTICE / ASSIGNMENTS
    # =========================================================

    path(
        "practice/",
        views.practice,
        name="practice"
    ),

    path(
        "assignments/",
        views.assignments,
        name="assignments"
    ),

    # =========================================================
    # PROJECTS
    # =========================================================

    path(
        "projects/",
        views.projects,
        name="projects"
    ),

    path(
        "projects/create/",
        views.create_project,
        name="create_project"
    ),

    path(
        "projects/<int:pk>/",
        views.project_detail,
        name="project_detail"
    ),

    path(
        "projects/<int:pk>/like/",
        views.project_like,
        name="project_like"
    ),

    path(
        "projects/<int:pk>/save/",
        views.project_save,
        name="project_save"
    ),

    path(
        "projects/<int:pk>/follow/",
        views.project_follow,
        name="project_follow"
    ),

    path(
        "projects/<int:pk>/comment/",
        views.project_comment,
        name="project_comment"
    ),

    path(
        "projects/comments/<int:pk>/like/",
        views.project_comment_like,
        name="project_comment_like"
    ),

    path(
        "projects/<int:pk>/update/",
        views.project_update,
        name="project_update"
    ),

    path(
        "projects/<int:pk>/collaborate/",
        views.project_collaborate,
        name="project_collaborate"
    ),

    path(
    "projects/<int:pk>/connect/",
    views.project_connect,
    name="project_connect"
    ),

    path(
        "projects/<int:pk>/report/",
        views.project_report,
        name="project_report"
    ),

    path(
        "projects/<int:pk>/share/",
        views.project_share,
        name="project_share"
    ),
# =========================================================
# MESSAGES
# =========================================================

path(
    "messages/",
    views.messages_list,
    name="messages"
),

path(
    "messages/<int:conversation_id>/",
    views.conversation_detail,
    name="conversation_detail"
),

path(
    "messages/delete/<int:message_id>/",
    views.delete_message,
    name="delete_message"
),

path(
    "messages/<int:conversation_id>/status/",
    views.conversation_status,
    name="conversation_status"
),
    # =========================================================
    # COMMUNITY
    # =========================================================

    path(
        "community/",
        views.community,
        name="community"
    ),
]