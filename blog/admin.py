from django.contrib import admin
from django.utils import timezone
from .models import (
    Post,
    Lesson,
    Assignment,
    AssignmentAudience,
    AssignmentAttempt,
    AssignmentOption,
    AssignmentQuestion,
    AssignmentSubmission,
    Comment,
    PracticeProblem,
    PracticeProgress,
    PracticeSubmission,
    UserAssignmentProgress,
    UserProfile,
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
        'author',
        'created_at',
        'image',
    )

    list_filter = (
        'category',
        'difficulty',
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


class LessonAdmin(admin.ModelAdmin):

    list_display = (
        'title',
        'course',
        'order',
        'created_at',
    )

    list_filter = (
        'course',
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
        ('Availability', {'fields': ('release_date', 'due_date', 'max_attempts', 'late_submission_allowed', 'required', 'status')}),
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
        'goal',
        'created_at',
        'updated_at',
    )

    list_filter = (
        'goal',
        'created_at',
    )

    search_fields = (
        'user__username',
        'user__email',
    )


admin.site.register(Post, PostAdmin)
admin.site.register(Lesson, LessonAdmin)
admin.site.register(Assignment, AssignmentAdmin)
admin.site.register(AssignmentSubmission, AssignmentSubmissionAdmin)
admin.site.register(Comment, CommentAdmin)
admin.site.register(UserProfile, UserProfileAdmin)