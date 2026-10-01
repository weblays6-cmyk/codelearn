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
        "course/<int:course_pk>/lesson/<int:lesson_pk>/start/",
        views.start_lesson_view,
        name="start_lesson"
    ),

    path(
        "lesson/<int:pk>/",
        views.lesson_detail,
        name="lesson_detail"
    ),

    path(
        "lesson/<int:pk>/complete/",
        views.complete_lesson,
        name="complete_lesson"
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
    "profile/<int:user_id>/followers/",
    views.followers_list,
    name="followers_list"
    ),

    path(
    "profile/<int:user_id>/following/",
    views.following_list,
    name="following_list"
    ),

        path(
        "profile/<int:user_id>/follow/",
        views.send_follow_request,
        name="send_follow_request"
    ),

    path(
        "profile/<int:user_id>/follow/cancel/",
        views.cancel_follow_request,
        name="cancel_follow_request"
    ),

    path(
        "follow-request/<int:request_id>/accept/",
        views.accept_follow_request,
        name="accept_follow_request"
    ),

    path(
        "follow-request/<int:request_id>/reject/",
        views.reject_follow_request,
        name="reject_follow_request"
    ),

    path(
        "profile/<int:user_id>/unfollow/",
        views.unfollow_user,
        name="unfollow_user"
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
        "practice/details/",
        views.practice_details,
        name="practice_details"
    ),

    path(
        "practice/problems/",
        views.practice_all,
        name="practice_all"
    ),

    path(
        "practice/playground/",
        views.practice_playground,
        name="practice_playground"
    ),

    path(
        "practice/playground/save/",
        views.playground_save,
        name="playground_save"
    ),

    path(
        "practice/playground/run/",
        views.playground_run,
        name="playground_run"
    ),

    path(
        "practice/mock-tests/",
        views.practice_mock_tests,
        name="practice_mock_tests"
    ),

    path(
        "practice/problem-sets/",
        views.practice_problem_sets,
        name="practice_problem_sets"
    ),

    path(
        "practice/problem-sets/<slug:slug>/",
        views.practice_problem_set_detail,
        name="practice_problem_set_detail"
    ),

    path(
        "practice/problems/<slug:slug>/",
        views.practice_problem_detail,
        name="practice_problem_detail"
    ),

    path(
        "practice/problems/<slug:slug>/run/",
        views.practice_problem_run,
        name="practice_problem_run"
    ),

    path(
        "practice/problems/<slug:slug>/submit/",
        views.practice_problem_submit,
        name="practice_problem_submit"
    ),

    path(
        "practice/mock-tests/<int:pk>/",
        views.practice_mock_test_detail,
        name="practice_mock_test_detail"
    ),

    path(
        "practice/mock-tests/<int:pk>/start/",
        views.practice_mock_test_start,
        name="practice_mock_test_start"
    ),

    path(
        "practice/mock-tests/attempt/<int:pk>/",
        views.practice_mock_test_attempt,
        name="practice_mock_test_attempt"
    ),

    path(
        "practice/mock-tests/attempt/<int:pk>/answer/",
        views.practice_mock_test_answer,
        name="practice_mock_test_answer"
    ),

    path(
        "practice/mock-tests/attempt/<int:pk>/submit/",
        views.practice_mock_test_submit,
        name="practice_mock_test_submit"
    ),

    path(
        "practice/mock-tests/attempt/<int:pk>/result/",
        views.practice_mock_test_result,
        name="practice_mock_test_result"
    ),

    path(
        "practice/leaderboard/",
        views.practice_leaderboard,
        name="practice_leaderboard"
    ),

    path(
        "practice/save-draft/",
        views.practice_save_draft,
        name="practice_save_draft"
    ),

    path(
        "practice/record/",
        views.practice_record,
        name="practice_record"
    ),

    path(
        "assignments/",
        views.assignments,
        name="assignments"
    ),

    path(
        "assignments/<int:pk>/",
        views.assignment_attempt,
        name="assignment_attempt"
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