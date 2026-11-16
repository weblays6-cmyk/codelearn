from django.conf import settings
from django.db.models import Q

from .models import Message, SiteSettings


def site_name(request):
    site_settings = SiteSettings.get_cached()
    user_theme_preference = 'light'
    if request.user.is_authenticated:
        user_theme_preference = getattr(
            getattr(request.user, 'profile_data', None),
            'theme_preference',
            'light',
        )
    match = getattr(request, 'resolver_match', None)
    route_context = {
        'lesson_detail': ('lesson', 'slug'),
        'practice_problem_detail': ('problem', 'slug'),
        'assignment_attempt': ('assignment', 'pk'),
        'project_detail': ('project', 'pk'),
        'community_post_detail': ('community', 'pk'),
    }
    context_type, context_key = route_context.get(getattr(match, 'url_name', None), ('', ''))
    context_id = getattr(match, 'kwargs', {}).get(context_key, '') if context_key else ''
    feature_flags = {
        'assistant': site_settings.ai_feature_assistant,
        'lesson_summary': site_settings.ai_feature_learning,
        'lesson_quiz': site_settings.ai_feature_learning,
        'roadmap': site_settings.ai_feature_learning,
        'explain_code': site_settings.ai_feature_learning,
        'code_review': site_settings.ai_feature_practice,
        'hint': site_settings.ai_feature_practice,
        'interview': site_settings.ai_feature_interview,
        'interview_report': site_settings.ai_feature_interview,
        'community_draft': site_settings.ai_feature_community,
        'duplicate_questions': site_settings.ai_feature_community,
        'daily_mission': site_settings.ai_feature_dashboard,
        'study_tip': site_settings.ai_feature_dashboard,
    }
    feature_labels = {
        'assistant': 'Ask a coding question',
        'lesson_summary': 'Summarize this lesson',
        'lesson_quiz': 'Create a lesson quiz',
        'roadmap': 'Build a learning path',
        'explain_code': 'Explain code',
        'code_review': 'Review code',
        'hint': 'Give me a hint',
        'interview': 'Interview practice',
        'interview_report': 'Interview feedback',
        'community_draft': 'Draft an answer',
        'duplicate_questions': 'Find similar questions',
        'daily_mission': 'Daily learning mission',
        'study_tip': 'Study tip',
    }
    return {
        'SITE_NAME': settings.SITE_NAME,
        'DEBUG': settings.DEBUG,
        'STATIC_BUILD_ID': settings.STATIC_BUILD_ID,
        'SITE_SETTINGS': site_settings,
        'DARK_THEME_ENABLED': site_settings.dark_theme_enabled,
        'AI_ENABLED': site_settings.ai_enabled,
        'AI_DAILY_LIMIT_FREE': site_settings.ai_daily_limit_free,
        'AI_DAILY_LIMIT_PREMIUM': site_settings.ai_daily_limit_premium,
        'USER_THEME_PREFERENCE': user_theme_preference,
        'AI_CONTEXT_TYPE': context_type,
        'AI_CONTEXT_ID': context_id,
        'AI_FEATURE_OPTIONS': [(feature, feature_labels[feature]) for feature, enabled in feature_flags.items() if enabled],
    }


def unread_message_count(request):

    if not request.user.is_authenticated:
        return {
            "UNREAD_MESSAGE_COUNT": 0
        }

    count = Message.objects.filter(
        Q(conversation__project_owner=request.user) |
        Q(conversation__participant=request.user),
        is_read=False
    ).exclude(
        sender=request.user
    ).count()

    return {
        "UNREAD_MESSAGE_COUNT": count
    }