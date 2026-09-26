from django.contrib import admin
from .models import Post, Lesson, Assignment, AssignmentSubmission, Comment, UserProfile


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
        'lesson',
        'max_score',
        'created_at',
    )

    list_filter = (
        'lesson',
        'created_at',
    )

    search_fields = (
        'title',
        'description',
        'lesson__title',
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