from django.urls import path
from django.views.generic import RedirectView
from . import views
from django.contrib.auth import views as auth_views


app_name = "blog"


urlpatterns = [

    # =========================================================
    # HOME / COURSES
    # =========================================================

    path(
        "",
        RedirectView.as_view(pattern_name="blog:login"),
        name="home"
    ),

    path(
        "courses/",
        views.blog,
        name="blogpage"
    ),

    path(
        "course/<slug:slug>/",
        views.post_detail,
        name="post_detail"
    ),

    path(
        "course/<slug:course_slug>/lesson/<slug:lesson_slug>/start/",
        views.start_lesson_view,
        name="start_lesson"
    ),

    path(
        "lesson/<slug:slug>/",
        views.lesson_detail,
        name="lesson_detail"
    ),

    path(
        "lesson/<slug:slug>/complete/",
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
        auth_views.LogoutView.as_view(next_page="/"),
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
        "profile/<str:username>/followers/",
        views.followers_list,
        name="followers_list"
    ),

    path(
        "profile/<str:username>/following/",
        views.following_list,
        name="following_list"
    ),

    path(
        "profile/<str:username>/follow/",
        views.send_follow_request,
        name="send_follow_request"
    ),

    path(
        "profile/<str:username>/follow/cancel/",
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
        "profile/<str:username>/unfollow/",
        views.unfollow_user,
        name="unfollow_user"
    ),

    path(
        "profile/<str:username>/block/",
        views.block_user,
        name="block_user"
    ),

    path(
        "profile/<str:username>/unblock/",
        views.unblock_user,
        name="unblock_user"
    ),

    path(
        "profile/<str:username>/",
        views.user_profile,
        name="user_profile"
    ),

    path(
        "profile/<str:username>/connect/",
        views.start_personal_chat,
        name="start_personal_chat"
    ),


    path(
        "settings/",
        views.settings_view,
        name="settings"
    ),

    path(
        "settings/password/",
        views.change_password,
        name="change_password"
    ),

    path(
        "account/deactivate/",
        views.deactivate_account,
        name="deactivate_account"
    ),

    path(
        "account/delete/",
        views.request_account_deletion,
        name="request_account_deletion"
    ),

    path(
        "account/recovery/",
        views.account_recovery,
        name="account_recovery"
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
    path(
        "ai-tutor/new/",
        views.ai_tutor_new_chat,
        name="ai_tutor_new",
    ),
    path(
        "ai-tutor/history/",
        views.ai_tutor_history,
        name="ai_tutor_history",
    ),
    path(
        "ai-tutor/history/clear/",
        views.ai_tutor_clear_history,
        name="ai_tutor_clear_history",
    ),
    path(
        "ai-tutor/history/<int:conversation_id>/",
        views.ai_tutor_conversation,
        name="ai_tutor_conversation",
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

    path(
        "global-search/",
        views.global_search,
        name="global_search"
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
    "people/",
    views.discover_users,
    name="discover_users"
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
    path(
        "community/create/",
        views.community_post_create,
        name="community_post_create",
    ),
    path(
        "community/posts/<int:pk>/",
        views.community_post_detail,
        name="community_post_detail",
    ),
    path(
        "community/posts/<int:pk>/edit/",
        views.community_post_edit,
        name="community_post_edit",
    ),
    path(
        "community/posts/<int:pk>/delete/",
        views.community_post_delete,
        name="community_post_delete",
    ),
    path(
        "community/posts/<int:pk>/reply/",
        views.community_reply_create,
        name="community_reply_create",
    ),
    path(
        "community/replies/<int:pk>/delete/",
        views.community_reply_delete,
        name="community_reply_delete",
    ),
    path(
        "community/replies/<int:pk>/edit/",
        views.community_reply_edit,
        name="community_reply_edit",
    ),
    path(
        "community/posts/<int:pk>/like/",
        views.community_post_like,
        name="community_post_like",
    ),
    path(
        "community/posts/<int:pk>/save/",
        views.community_post_save,
        name="community_post_save",
    ),
]