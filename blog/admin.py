from django.contrib import admin
from .device_sessions import enforce_device_limit
from django.utils import timezone
from .models import (
    Post,
    Lesson,
    SubscriptionPlan,
    Payment,
    Assignment,
    AssignmentAudience,
    AssignmentAttempt,
    AssignmentOption,
    AssignmentQuestion,
    AssignmentSubmission,
    Comment,
    CommunityPost,
    CommunityReply,
    CommunityReport,
    CommunityFollow,
    Project,
    ProjectReport,
    ProjectIdea,
    AIRoadmap,
    AISavedContent,
    AIUsage,
    PracticeProblem,
    PracticeProgress,
    PracticeSubmission,
    UserAssignmentProgress,
    UserProfile,
    SiteSettings,
    UserSession,
    UserLoginSession,
)


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    ordering = ('order',)


class PostAdmin(admin.ModelAdmin):

    list_display = (
        'title',
        'category',
        'difficulty',
        'access',
        'price',
        'required_plan',
        'author',
        'created_at',
        'image',
    )

    list_filter = (
        'category',
        'difficulty',
        'access',
        'created_at',
    )

    search_fields = (
        'title',
        'content',
        'description',
        'what_you_learn',
        'author__username',
    )

    inlines = [LessonInline]
    list_editable = ('access', 'price', 'required_plan')

    def save_model(self, request, obj, form, change):
        obj.is_free = obj.access == 'free'
        super().save_model(request, obj, form, change)


class LessonAdmin(admin.ModelAdmin):

    list_display = (
        'title',
        'course',
        'level',
        'order',
        'created_at',
    )

    list_filter = (
        'course',
        'level',
        'created_at',
    )

    search_fields = (
        'title',
        'content',
        'course__title',
    )

    ordering = (
        'course',
        'order',
    )


class AssignmentAdmin(admin.ModelAdmin):

    list_display = (
        'title',
        'assignment_source',
        'assignment_type',
        'course',
        'lesson',
        'status',
        'created_at',
    )

    list_filter = (
        'assignment_source',
        'assignment_type',
        'status',
        'lesson',
        'course',
        'created_at',
    )

    search_fields = (
        'title',
        'description',
        'lesson__title',
        'course__title',
    )

    fieldsets = (
        (None, {'fields': ('title', 'description', 'instructions')}),
        ('Source and placement', {'fields': ('assignment_source', 'course', 'lesson')}),
        ('Execution', {'fields': ('assignment_type', 'difficulty', 'max_score', 'passing_marks', 'estimated_duration')}),
        ('Rubric', {'fields': ('rubric',)}),
        ('Availability', {'fields': ('release_date', 'due_date', 'max_attempts', 'late_submission_allowed', 'late_grace_minutes', 'late_penalty_percent', 'required', 'status')}),
        ('Ownership', {'fields': ('created_by', 'published_at')}),
    )


class AssignmentSubmissionAdmin(admin.ModelAdmin):

    list_display = (
        'student',
        'assignment',
        'status',
        'score',
        'submitted_at',
        'evaluated_by',
    )

    list_filter = (
        'status',
        'assignment',
        'submitted_at',
    )

    search_fields = (
        'student__username',
        'assignment__title',
        'answer',
        'feedback',
    )

    def save_model(self, request, obj, form, change):
        if obj.score is not None:
            obj.status = 'Evaluated'
            obj.evaluated_by = request.user
            obj.evaluated_at = obj.evaluated_at or timezone.now()
        super().save_model(request, obj, form, change)

        if obj.status == 'Evaluated' and obj.score is not None:
            attempt = AssignmentAttempt.objects.filter(
                assignment=obj.assignment,
                user=obj.student,
                status='SUBMITTED',
            ).order_by('-attempt_number').first()
            progress, _ = UserAssignmentProgress.objects.get_or_create(
                assignment=obj.assignment,
                user=obj.student,
            )
            if attempt:
                attempt.score = obj.score
                attempt.max_score = obj.assignment.max_score
                attempt.percentage = round(obj.score * 100 / attempt.max_score) if attempt.max_score else 0
                attempt.passed = obj.score >= obj.assignment.passing_marks
                attempt.feedback = obj.feedback
                attempt.status = 'EVALUATED'
                attempt.evaluated_at = obj.evaluated_at
                attempt.save()
                if progress.latest_attempt_id == attempt.id:
                    progress.status = 'PASSED' if attempt.passed else 'FAILED'
                    progress.best_score = max(progress.best_score or 0, obj.score)
                    progress.evaluated_at = obj.evaluated_at
                    progress.completed_at = obj.evaluated_at if attempt.passed else None
                    progress.save(update_fields=(
                        'status', 'best_score', 'evaluated_at', 'completed_at'
                    ))


@admin.register(AssignmentAudience)
class AssignmentAudienceAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'audience_type', 'user')
    list_filter = ('audience_type',)
    search_fields = ('assignment__title', 'user__username')


@admin.register(UserAssignmentProgress)
class UserAssignmentProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'assignment', 'status', 'best_score', 'attempts_used')
    list_filter = ('status',)
    search_fields = ('user__username', 'assignment__title')


@admin.register(AssignmentAttempt)
class AssignmentAttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'assignment', 'attempt_number', 'status', 'score', 'submitted_at')
    list_filter = ('status', 'assignment__assignment_source')
    search_fields = ('user__username', 'assignment__title')


@admin.register(AssignmentQuestion)
class AssignmentQuestionAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'order', 'question_type', 'marks')
    list_filter = ('question_type',)
    search_fields = ('assignment__title', 'question')


@admin.register(AssignmentOption)
class AssignmentOptionAdmin(admin.ModelAdmin):
    list_display = ('question', 'order', 'is_correct')
    list_filter = ('is_correct',)
    search_fields = ('option_text', 'question__question')


@admin.register(PracticeProblem)
class PracticeProblemAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'category', 'difficulty', 'active', 'updated_at')
    list_filter = ('category', 'difficulty', 'active')
    search_fields = ('title', 'slug', 'description')


@admin.register(PracticeProgress)
class PracticeProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'problem', 'status', 'attempt_count', 'last_attempt_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'problem__title')


@admin.register(PracticeSubmission)
class PracticeSubmissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'problem', 'language', 'status', 'submitted_at')
    list_filter = ('status', 'language')
    search_fields = ('user__username', 'problem__title')


class CommentAdmin(admin.ModelAdmin):

    list_display = (
        'author',
        'post',
        'created_at',
    )

    list_filter = (
        'created_at',
    )

    search_fields = (
        'content',
        'author__username',
        'post__title',
    )


class UserProfileAdmin(admin.ModelAdmin):

    list_display = (
        'user',
        'plan',
        'subscription_plan',
        'plan_expires_at',
        'goal',
        'is_test_account',
        'leaderboard_opt_in',
        'show_public_badges',
        'created_at',
        'updated_at',
    )

    list_filter = (
        'plan',
        'subscription_plan',
        'goal',
        'is_test_account',
        'leaderboard_opt_in',
        'show_public_badges',
        'created_at',
    )

    search_fields = (
        'user__username',
        'user__email',
    )

    actions = ('grant_premium', 'revoke_premium')

    @admin.action(description='Grant premium plan')
    def grant_premium(self, request, queryset):
        queryset.update(plan='premium', plan_expires_at=None)

    @admin.action(description='Revoke premium plan')
    def revoke_premium(self, request, queryset):
        queryset.update(plan='free', plan_expires_at=None, subscription_plan=None)
        for profile in queryset.select_related('user'):
            enforce_device_limit(profile.user)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        enforce_device_limit(obj.user)


admin.site.register(Post, PostAdmin)
admin.site.register(Lesson, LessonAdmin)
admin.site.register(Assignment, AssignmentAdmin)
admin.site.register(AssignmentSubmission, AssignmentSubmissionAdmin)
admin.site.register(Comment, CommentAdmin)
admin.site.register(UserProfile, UserProfileAdmin)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'currency', 'duration_days', 'is_active', 'updated_at')
    list_filter = ('is_active', 'currency')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'amount', 'currency', 'status', 'provider', 'created_at', 'paid_at')
    list_filter = ('status', 'provider', 'currency', 'created_at')
    search_fields = ('user__username', 'provider_order_id', 'provider_id')
    readonly_fields = ('provider_order_id', 'provider_id', 'idempotency_key', 'created_at', 'updated_at', 'paid_at')


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'dark_theme_enabled',
        'ai_enabled',
        'ai_daily_limit_free',
        'ai_daily_limit_premium',
        'ai_feature_assistant',
        'ai_feature_learning',
        'ai_feature_practice',
        'ai_feature_interview',
        'ai_feature_community',
        'ai_feature_dashboard',
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'device_label', 'ip', 'created_at', 'last_seen', 'is_active')
    list_filter = ('is_active', 'created_at')
    search_fields = ('user__username', 'device_label', 'ip')
    exclude = ('session_key',)

    def has_add_permission(self, request):
        return False


@admin.register(UserLoginSession)
class UserLoginSessionAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'device_description',
        'login_at',
        'last_activity_at',
        'expires_at',
        'is_active',
    )
    list_filter = ('is_active', 'login_at')
    search_fields = ('user__username', 'device_description')
    actions = ('revoke_selected_sessions',)

    @admin.action(description='Revoke selected login sessions')
    def revoke_selected_sessions(self, request, queryset):
        revoked_count = queryset.filter(is_active=True).update(
            is_active=False,
            revoked_at=timezone.now(),
        )
        self.message_user(request, f'Revoked {revoked_count} login session(s).')

    def has_add_permission(self, request):
        return False


@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'author', 'created_at')
    list_filter = ('category', 'created_at')
    search_fields = ('title', 'content', 'author__username')


@admin.register(CommunityReply)
class CommunityReplyAdmin(admin.ModelAdmin):
    list_display = ('post', 'author', 'created_at')
    search_fields = ('content', 'author__username', 'post__title')


@admin.register(CommunityReport)
class CommunityReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'reporter', 'post', 'reply', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('reason', 'details', 'reporter__username', 'post__title', 'reply__content')
    readonly_fields = ('reporter', 'post', 'reply', 'reason', 'details', 'created_at')


@admin.register(ProjectReport)
class ProjectReportAdmin(admin.ModelAdmin):
    list_display = ('project', 'reporter', 'status', 'created_at', 'moderator')
    list_filter = ('status', 'created_at')
    search_fields = ('project__title', 'reporter__username', 'reason', 'description')
    readonly_fields = ('project', 'reporter', 'reason', 'description', 'created_at')


@admin.register(ProjectIdea)
class ProjectIdeaAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'tech_stack', 'created_at')
    search_fields = ('title', 'description', 'author__username', 'tech_stack')
    readonly_fields = ('author', 'created_at')


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'category', 'publication_status', 'is_public', 'is_featured')
    list_filter = ('category', 'publication_status', 'is_public', 'is_featured')
    search_fields = ('title', 'short_description', 'description', 'owner__username')


@admin.register(AIUsage)
class AIUsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'feature', 'created_at', 'cached')
    list_filter = ('feature', 'cached', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('user', 'feature', 'created_at', 'cached')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AIRoadmap)
class AIRoadmapAdmin(admin.ModelAdmin):
    list_display = ('user', 'updated_at')
    search_fields = ('user__username',)


@admin.register(AISavedContent)
class AISavedContentAdmin(admin.ModelAdmin):
    list_display = ('user', 'feature', 'created_at')
    list_filter = ('feature', 'created_at')
    search_fields = ('user__username',)


@admin.register(CommunityFollow)
class CommunityFollowAdmin(admin.ModelAdmin):
    list_display = ('post', 'user', 'created_at')
    search_fields = ('post__title', 'user__username')