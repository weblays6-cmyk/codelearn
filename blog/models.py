from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.utils.text import slugify
from django.utils import timezone
from django.utils.deconstruct import deconstructible
import uuid


class PreserveOriginalFilenameStorage(FileSystemStorage):
    def get_available_name(self, name, max_length=None):
        if self.exists(name):
            self.delete(name)
        return name


@deconstructible
class PrivateMessageStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(
            location=settings.BASE_DIR / 'private_message_attachments',
            base_url=None,
        )


# =========================================================
# COURSE / POST
# =========================================================

class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='INR')
    duration_days = models.PositiveSmallIntegerField(default=30)
    features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('price', 'name')

    def __str__(self):
        return self.name

class Post(models.Model):

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PUBLISHED', 'Published'),
        ('ARCHIVED', 'Archived'),
    ]

    CATEGORY_CHOICES = [
        ('Python', 'Python'),
        ('Django', 'Django'),
        ('AI', 'AI'),
        ('Java', 'Java'),
        ('JavaScript', 'JavaScript'),
        ('C++', 'C++'),
        ('C#', 'C#'),
        ('PHP', 'PHP'),
        ('Ruby', 'Ruby'),
        ('Go', 'Go'),
        ('Swift', 'Swift'),
        ('Kotlin', 'Kotlin'),
        ('Rust', 'Rust'),
        ('TypeScript', 'TypeScript'),
        ('SQL', 'SQL'),
        ('HTML/CSS', 'HTML/CSS'),
        ('Other', 'Other'),
    ]

    DIFFICULTY_CHOICES = [
        ('Beginner', 'Beginner'),
        ('Intermediate', 'Intermediate'),
        ('Advanced', 'Advanced'),
    ]
    ACCESS_CHOICES = [
        ('free', 'Free'),
        ('paid', 'Paid'),
    ]

    title = models.CharField(
        max_length=100
    )

    slug = models.SlugField(
        max_length=180,
        unique=True,
        blank=True,
    )

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='Python'
    )

    description = models.TextField(
        blank=True
    )

    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default='Beginner'
    )

    duration_minutes = models.PositiveSmallIntegerField(default=0)

    access = models.CharField(max_length=8, choices=ACCESS_CHOICES, default='free')
    required_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        related_name='courses',
        null=True,
        blank=True,
    )
    is_free = models.BooleanField(default=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    what_you_learn = models.TextField(
        blank=True
    )

    prerequisites = models.TextField(blank=True)

    content = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PUBLISHED',
    )

    sequential_learning = models.BooleanField(default=False)

    image = models.ImageField(
        upload_to='posts/',
        blank=True,
        null=True
    )

    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or f'course-{self.pk or "new"}'
            candidate = base_slug
            suffix = 2
            while Post.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f'{base_slug}-{suffix}'
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


# =========================================================
# COURSE MODULE
# =========================================================

class Module(models.Model):

    course = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='modules',
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.course.title} - {self.title}"


# =========================================================
# LESSON
# =========================================================

class Lesson(models.Model):
    LEVEL_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]

    course = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='lessons'
    )

    module = models.ForeignKey(
        Module,
        on_delete=models.SET_NULL,
        related_name='lessons',
        null=True,
        blank=True,
    )

    title = models.CharField(
        max_length=200
    )

    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True,
    )

    content = models.TextField()

    level = models.CharField(max_length=12, choices=LEVEL_CHOICES, default='beginner')

    video_url = models.URLField(
        blank=True,
        null=True
    )

    order = models.PositiveIntegerField(
        default=1
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ['order']

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or f'lesson-{self.pk or "new"}'
            candidate = base_slug
            suffix = 2
            while Lesson.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f'{base_slug}-{suffix}'
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.course.title} - {self.title}"


# =========================================================
# ASSIGNMENT
# =========================================================

class Assignment(models.Model):

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='assignments',
        null=True,
        blank=True
    )

    course = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='assignments',
        null=True,
        blank=True
    )

    SOURCE_CHOICES = [
        ('STANDALONE', 'Standalone'),
        ('COURSE', 'Course'),
    ]
    TYPE_CHOICES = [
        ('QUIZ', 'Quiz'),
        ('CODING', 'Coding'),
        ('TEXT', 'Text'),
        ('FILE_UPLOAD', 'File upload'),
        ('PROJECT', 'Project'),
    ]
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PUBLISHED', 'Published'),
        ('ARCHIVED', 'Archived'),
    ]

    title = models.CharField(
        max_length=200
    )

    description = models.TextField()

    instructions = models.TextField(blank=True)
    assignment_source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='COURSE')
    assignment_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='TEXT')
    difficulty = models.CharField(max_length=20, default='Beginner')

    max_score = models.PositiveIntegerField(
        default=100
    )

    passing_marks = models.PositiveIntegerField(default=50)
    estimated_duration = models.PositiveIntegerField(default=30)
    release_date = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    max_attempts = models.PositiveIntegerField(default=1)
    late_submission_allowed = models.BooleanField(default=False)
    late_grace_minutes = models.PositiveSmallIntegerField(default=0)
    late_penalty_percent = models.PositiveSmallIntegerField(default=0)
    rubric = models.JSONField(default=list, blank=True)
    required = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_assignments')
    published_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        indexes = [
            models.Index(fields=('status', 'due_date'), name='assignment_status_due_idx'),
            models.Index(fields=('assignment_source', 'status'), name='assignment_source_status_idx'),
        ]

    def clean(self):
        errors = {}

        if self.assignment_source == 'COURSE' and not self.course and not self.lesson:
            errors['course'] = 'Course assignments must be linked to a course or lesson.'

        if self.assignment_source == 'STANDALONE' and (self.course or self.lesson):
            errors['assignment_source'] = 'Standalone assignments cannot be linked to a course or lesson.'

        if self.course and self.lesson and self.lesson.course_id != self.course_id:
            errors['lesson'] = 'The selected lesson must belong to the selected course.'

        if self.late_penalty_percent > 100:
            errors['late_penalty_percent'] = 'The late penalty cannot exceed 100 percent.'

        if not isinstance(self.rubric, list):
            errors['rubric'] = 'Rubric criteria must be a list.'
        else:
            criterion_names = []
            total_points = 0
            for criterion in self.rubric:
                if not isinstance(criterion, dict) or not str(criterion.get('name', '')).strip():
                    errors['rubric'] = 'Each rubric criterion needs a name and points value.'
                    break
                try:
                    points = int(criterion.get('points', 0))
                except (TypeError, ValueError):
                    errors['rubric'] = 'Rubric points must be whole numbers.'
                    break
                name = str(criterion['name']).strip()
                if points < 0 or name in criterion_names:
                    errors['rubric'] = 'Rubric points must be non-negative and criterion names unique.'
                    break
                criterion_names.append(name)
                total_points += points
            if not errors.get('rubric') and total_points > self.max_score:
                errors['rubric'] = 'Rubric points cannot exceed the assignment maximum score.'

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        parent = self.lesson or self.course
        return f"{parent} - {self.title}" if parent else self.title


class AssignmentAudience(models.Model):

    AUDIENCE_CHOICES = [
        ('ALL_USERS', 'All users'),
        ('SELECTED_USER', 'Selected user'),
    ]

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='audiences')
    audience_type = models.CharField(max_length=20, choices=AUDIENCE_CHOICES)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='assignment_audiences')

    class Meta:
        constraints = [models.UniqueConstraint(fields=('assignment', 'audience_type', 'user'), name='unique_assignment_audience')]


class UserAssignmentProgress(models.Model):

    STATUS_CHOICES = [
        ('NOT_STARTED', 'Not started'),
        ('IN_PROGRESS', 'In progress'),
        ('SUBMITTED', 'Submitted'),
        ('EVALUATED', 'Evaluated'),
        ('PASSED', 'Passed'),
        ('FAILED', 'Failed'),
        ('OVERDUE', 'Overdue'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assignment_progress')
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='progress_records')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NOT_STARTED')
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    best_score = models.PositiveIntegerField(null=True, blank=True)
    attempts_used = models.PositiveIntegerField(default=0)
    latest_attempt = models.ForeignKey('AssignmentAttempt', on_delete=models.SET_NULL, null=True, blank=True, related_name='latest_for_progress')

    class Meta:
        constraints = [models.UniqueConstraint(fields=('user', 'assignment'), name='unique_user_assignment_progress')]


class AssignmentAttempt(models.Model):

    STATUS_CHOICES = [
        ('IN_PROGRESS', 'In progress'),
        ('SUBMITTED', 'Submitted'),
        ('EVALUATED', 'Evaluated'),
    ]

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assignment_attempts')
    attempt_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_PROGRESS')
    answer_data = models.JSONField(default=dict, blank=True)
    source_code = models.TextField(blank=True)
    language = models.CharField(max_length=30, blank=True)
    score = models.PositiveIntegerField(null=True, blank=True)
    max_score = models.PositiveIntegerField(default=0)
    percentage = models.PositiveIntegerField(null=True, blank=True)
    passed = models.BooleanField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_saved_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('assignment', 'user', 'attempt_number'), name='unique_assignment_attempt_number')]


class AssignmentQuestion(models.Model):

    QUESTION_TYPES = [
        ('SINGLE', 'Single choice'),
        ('MULTIPLE', 'Multiple choice'),
        ('TRUE_FALSE', 'True/false'),
    ]

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='questions')
    question = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='SINGLE')
    marks = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.assignment.title} - Question {self.order}"


class AssignmentOption(models.Model):

    question = models.ForeignKey(AssignmentQuestion, on_delete=models.CASCADE, related_name='options')
    option_text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.question} - Option {self.order}"


# =========================================================
# ASSIGNMENT SUBMISSION
# =========================================================

class AssignmentSubmission(models.Model):

    STATUS_CHOICES = [
        ('Submitted', 'Submitted'),
        ('Evaluated', 'Evaluated'),
    ]

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='submissions'
    )

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='assignment_submissions'
    )

    answer = models.TextField(
        blank=True
    )

    file = models.FileField(
        upload_to='assignments/',
        storage=PreserveOriginalFilenameStorage(),
        blank=True,
        null=True
    )

    submitted_at = models.DateTimeField(
        auto_now_add=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Submitted'
    )

    score = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    feedback = models.TextField(
        blank=True
    )
    rubric_feedback = models.JSONField(default=dict, blank=True)
    is_late = models.BooleanField(default=False)

    evaluated_at = models.DateTimeField(
        null=True,
        blank=True
    )

    evaluated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='evaluated_submissions'
    )

    def __str__(self):
        return f"{self.student.username} - {self.assignment.title}"


# =========================================================
# COMMENT
# =========================================================

class Comment(models.Model):

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE
    )

    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    content = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    likes = models.ManyToManyField(
        User,
        related_name='liked_posts',
        blank=True
    )

    def __str__(self):
        return self.author.username


class CommunityPost(models.Model):

    title = models.CharField(max_length=180)
    content = models.TextField()
    category = models.CharField(
        max_length=20,
        choices=Post.CATEGORY_CHOICES,
        default='Other',
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='community_posts',
    )
    liked_by = models.ManyToManyField(
        User,
        related_name='liked_community_posts',
        blank=True,
    )
    saved_by = models.ManyToManyField(
        User,
        related_name='saved_community_posts',
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tags = models.JSONField(default=list, blank=True)
    accepted_reply = models.ForeignKey(
        'CommunityReply',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accepted_for_posts',
    )
    is_hidden = models.BooleanField(default=False)
    toxicity_flagged = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category', '-created_at']),
        ]

    def __str__(self):
        return self.title


class CommunityReply(models.Model):

    post = models.ForeignKey(
        CommunityPost,
        on_delete=models.CASCADE,
        related_name='replies',
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='community_replies',
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_accepted = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)
    toxicity_flagged = models.BooleanField(default=False)


class CommunityReport(models.Model):
    STATUS_CHOICES = (
        ('OPEN', 'Open'),
        ('REVIEWED', 'Reviewed'),
        ('DISMISSED', 'Dismissed'),
    )
    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, null=True, blank=True, related_name='reports')
    reply = models.ForeignKey(CommunityReply, on_delete=models.CASCADE, null=True, blank=True, related_name='reports')
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='community_reports')
    reason = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='OPEN', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(post__isnull=False, reply__isnull=True) | models.Q(post__isnull=True, reply__isnull=False)),
                name='community_report_one_target',
            ),
            models.UniqueConstraint(fields=('post', 'reporter'), condition=models.Q(post__isnull=False), name='unique_community_post_report'),
            models.UniqueConstraint(fields=('reply', 'reporter'), condition=models.Q(reply__isnull=False), name='unique_community_reply_report'),
        ]


class CommunityFollow(models.Model):
    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='followers')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='followed_community_posts')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        constraints = [models.UniqueConstraint(fields=('post', 'user'), name='unique_community_follow')]

    def __str__(self):
        return f'{self.user.username} follows {self.post.title}'


# =========================================================
# USER PROFILE
# =========================================================

class UserProfile(models.Model):

    GOAL_CHOICES = [
        ('full_stack', 'Python Full Stack Developer'),
        ('django', 'Django Developer'),
        ('data', 'Data Analyst'),
        ('interview', 'Interview Prep'),
        ('web', 'Web Basics'),
    ]
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('premium', 'Premium'),
    ]
    THEME_PREFERENCE_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
        ('system', 'System'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile_data'
    )

    display_name = models.CharField(
        max_length=150,
        blank=True,
        default=''
    )
    headline = models.CharField(max_length=160, blank=True)
    location = models.CharField(max_length=120, blank=True)
    bio = models.TextField(max_length=2000, blank=True)
    skills = models.JSONField(default=list, blank=True)
    github_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    portfolio_url = models.URLField(blank=True)
    profile_banner = models.ImageField(upload_to='profile_banners/', blank=True, null=True)
    font_size = models.CharField(max_length=10, choices=(('small', 'Small'), ('default', 'Default'), ('large', 'Large')), default='default')
    reduce_motion = models.BooleanField(default=False)
    swipe_navigation = models.BooleanField(default=False)
    timezone_name = models.CharField(max_length=64, default='UTC')
    language_preference = models.CharField(max_length=12, default='en')
    notify_follows = models.BooleanField(default=True)
    notify_messages = models.BooleanField(default=True)
    notify_community = models.BooleanField(default=True)
    notify_assignments = models.BooleanField(default=True)
    notify_system = models.BooleanField(default=True)
    email_notifications = models.BooleanField(default=False)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    desktop_notifications = models.BooleanField(default=False)

    plan = models.CharField(
        max_length=10,
        choices=PLAN_CHOICES,
        default='free',
    )
    plan_expires_at = models.DateTimeField(null=True, blank=True)
    subscription_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        related_name='subscribers',
        null=True,
        blank=True,
    )
    theme_preference = models.CharField(
        max_length=10,
        choices=THEME_PREFERENCE_CHOICES,
        default='light',
    )
    notification_sound = models.BooleanField(default=False)
    message_sound = models.BooleanField(default=False)
    WHO_CAN_MESSAGE_CHOICES = [
        ('everyone', 'Everyone'),
        ('followers', 'People who follow me or whom I follow'),
        ('mutual', 'Mutual followers'),
        ('nobody', 'Nobody'),
    ]
    who_can_message = models.CharField(
        max_length=12,
        choices=WHO_CAN_MESSAGE_CHOICES,
        default='mutual',
    )
    is_online_visible = models.BooleanField(default=True)

    profile_picture = models.ImageField(
        upload_to='profile_pictures/',
        blank=True,
        null=True
    )

    is_private = models.BooleanField(
        default=False
    )

    leaderboard_opt_in = models.BooleanField(default=False)
    show_public_badges = models.BooleanField(default=True)
    is_test_account = models.BooleanField(default=False)
    DAILY_TASK_GOAL_CHOICES = [
        (1, '1 task'),
        (3, '3 tasks'),
        (5, '5 tasks'),
    ]
    daily_task_goal = models.PositiveSmallIntegerField(
        choices=DAILY_TASK_GOAL_CHOICES,
        default=3,
    )

    goal = models.CharField(
        max_length=20,
        choices=GOAL_CHOICES,
        blank=True,
        null=True
    )

    onboarding_completed = models.BooleanField(
        default=True
    )

    is_deactivated = models.BooleanField(
        default=False
    )

    deactivated_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    deletion_requested_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    scheduled_deletion_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.user.username

    def get_goal_display_label(self):
        if self.goal == 'django_dev':
            return 'Django Developer'
        return self.get_goal_display() if self.goal else 'Not selected'


class Payment(models.Model):
    STATUS_CHOICES = [
        ('created', 'Created'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_payments')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='payments')
    course = models.ForeignKey(Post, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='created')
    provider = models.CharField(max_length=24, default='razorpay')
    provider_order_id = models.CharField(max_length=128, blank=True, null=True, unique=True)
    provider_id = models.CharField(max_length=128, blank=True, null=True, unique=True)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.user} - {self.plan} - {self.status}'


class SiteSettings(models.Model):
    dark_theme_enabled = models.BooleanField(default=False)
    ai_enabled = models.BooleanField(default=True)
    ai_daily_limit_free = models.PositiveSmallIntegerField(default=30)
    ai_daily_limit_premium = models.PositiveSmallIntegerField(default=200)
    ai_feature_assistant = models.BooleanField(default=True)
    ai_feature_learning = models.BooleanField(default=True)
    ai_feature_practice = models.BooleanField(default=True)
    ai_feature_interview = models.BooleanField(default=True)
    ai_feature_community = models.BooleanField(default=True)
    ai_feature_dashboard = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Site settings'
        verbose_name_plural = 'Site settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete('blog.site_settings')

    def delete(self, *args, **kwargs):
        cache.delete('blog.site_settings')

    @classmethod
    def get_cached(cls):
        settings_obj = cache.get('blog.site_settings')
        if settings_obj is None:
            settings_obj, _ = cls.objects.get_or_create(pk=1)
            cache.set('blog.site_settings', settings_obj, 300)
        return settings_obj

    def __str__(self):
        return 'Site settings'


class UserSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='device_sessions',
    )
    session_key = models.CharField(max_length=40, unique=True)
    device_label = models.CharField(max_length=120)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('-last_seen',)
        indexes = [models.Index(fields=('user', 'is_active'))]

    def __str__(self):
        return f'{self.user.username} - {self.device_label}'


class LoginHistory(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='login_history',
    )
    device_label = models.CharField(max_length=120)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        indexes = [models.Index(fields=('user', '-created_at'))]

    def __str__(self):
        return f'{self.user.username} logged in from {self.device_label}'


# =========================================================
# COURSE ENROLLMENT
# =========================================================

class Enrollment(models.Model):

    STATUS_CHOICES = [
        ('ENROLLED', 'Enrolled'),
        ('IN_PROGRESS', 'In progress'),
        ('COMPLETED', 'Completed'),
    ]

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )

    course = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='enrolled_students'
    )

    enrolled_at = models.DateTimeField(
        auto_now_add=True
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ENROLLED')
    started_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    progress = models.PositiveIntegerField(
        default=0
    )

    completed = models.BooleanField(
        default=False
    )
    certificate_code = models.CharField(
        max_length=40,
        unique=True,
        null=True,
        blank=True,
        default=None,
        editable=False,
    )

    class Meta:
        unique_together = ('student', 'course')
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.student.username} - {self.course.title}"


# =========================================================
# LESSON PROGRESS
# =========================================================

class LessonProgress(models.Model):

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='lesson_progress'
    )

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='student_progress'
    )

    completed = models.BooleanField(
        default=False
    )

    started_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        unique_together = ('student', 'lesson')
        ordering = ['-completed_at']

    def __str__(self):
        return f"{self.student.username} - {self.lesson.title}"


class CourseWishlist(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_courses')
    course = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='wishlisted_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('user', 'course'), name='unique_user_saved_course'),
        ]
        indexes = [models.Index(fields=('user', '-created_at'))]


class CourseReview(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_reviews')
    course = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField()
    review = models.TextField(blank=True, max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('user', 'course'), name='unique_user_course_review'),
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name='course_review_rating_1_to_5'),
        ]
        indexes = [models.Index(fields=('course', 'rating'))]


class LessonNote(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_notes')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='notes', db_index=False)
    content = models.TextField(max_length=10000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('user', 'lesson'), name='unique_user_lesson_note'),
        ]
        indexes = [
            models.Index(fields=('user', '-updated_at')),
            models.Index(fields=('lesson',), name='blog_lnote_lesson_idx'),
        ]


class LessonBookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_bookmarks')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='bookmarks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('user', 'lesson'), name='unique_user_lesson_bookmark'),
        ]


class ModuleQuiz(models.Model):
    module = models.OneToOneField(Module, on_delete=models.CASCADE, related_name='quiz')
    title = models.CharField(max_length=200)
    passing_score = models.PositiveSmallIntegerField(default=70)

    def __str__(self):
        return self.title


class QuizQuestion(models.Model):
    quiz = models.ForeignKey(ModuleQuiz, on_delete=models.CASCADE, related_name='questions')
    prompt = models.CharField(max_length=500)
    options = models.JSONField(default=list)
    correct_option = models.PositiveSmallIntegerField()
    explanation = models.TextField(blank=True, max_length=2000)
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ('order', 'pk')
        constraints = [
            models.UniqueConstraint(fields=('quiz', 'order'), name='unique_quiz_question_order'),
        ]


class QuizAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='quiz_attempts')
    quiz = models.ForeignKey(ModuleQuiz, on_delete=models.CASCADE, related_name='attempts')
    score = models.PositiveSmallIntegerField(default=0)
    passed = models.BooleanField(default=False)
    answers = models.JSONField(default=dict)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=('user', 'quiz', '-attempted_at'))]


class CourseCertificate(models.Model):
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='certificate')
    verification_code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    issued_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.enrollment.student} - {self.enrollment.course}'


# =========================================================
# DEVELOPER PROJECT
# =========================================================

class Project(models.Model):

    PUBLICATION_CHOICES = (('DRAFT', 'Draft'), ('PUBLISHED', 'Published'))
    STATUS_CHOICES = [
        ("idea", "Idea"),
        ("development", "In Development"),
        ("completed", "Completed"),
        ("live", "Live"),
    ]

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="projects"
    )

    title = models.CharField(
        max_length=200
    )

    short_description = models.CharField(
        max_length=300
    )

    description = models.TextField()

    category = models.CharField(
        max_length=100
    )

    tech_stack = models.CharField(
        max_length=500,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="idea"
    )

    problem = models.TextField(
        blank=True
    )

    features = models.TextField(
        blank=True
    )

    github_url = models.URLField(
        blank=True
    )

    live_demo_url = models.URLField(
        blank=True
    )

    looking_for_collaborators = models.BooleanField(
        default=False
    )
    is_public = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    publication_status = models.CharField(max_length=12, choices=PUBLICATION_CHOICES, default='PUBLISHED', db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    collaborator_types = models.CharField(
        max_length=500,
        blank=True
    )

    original_description = models.TextField(
        blank=True
    )

    ai_improved_description = models.TextField(
        blank=True
    )

    ai_improved = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.title


# =========================================================
# PROJECT IMAGES
# =========================================================

class ProjectImage(models.Model):

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="images"
    )

    image = models.ImageField(
        upload_to="projects/"
    )

    alt_text = models.CharField(
        max_length=200,
        blank=True
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.project.title} Image"


# =========================================================
# PROJECT LIKES
# =========================================================

class ProjectLike(models.Model):

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="likes"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="project_likes"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user"],
                name="unique_project_like"
            )
        ]

    def __str__(self):
        return f"{self.user.username} liked {self.project.title}"


# =========================================================
# PROJECT COMMENTS
# =========================================================

class ProjectComment(models.Model):

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="comments"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="project_comments"
    )

    content = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"{self.user.username} - {self.project.title}"


# =========================================================
# PROJECT COMMENT LIKES
# =========================================================

class ProjectCommentLike(models.Model):

    comment = models.ForeignKey(
        ProjectComment,
        on_delete=models.CASCADE,
        related_name="likes"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="project_comment_likes"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["comment", "user"],
                name="unique_project_comment_like"
            )
        ]

    def __str__(self):
        return f"{self.user.username} liked comment"


# =========================================================
# PROJECT SAVES
# =========================================================

class ProjectSave(models.Model):

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="saves"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="saved_projects"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user"],
                name="unique_project_save"
            )
        ]

    def __str__(self):
        return f"{self.user.username} saved {self.project.title}"


# =========================================================
# PROJECT FOLLOWS
# =========================================================

class ProjectFollow(models.Model):

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="followers"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="followed_projects"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user"],
                name="unique_project_follow"
            )
        ]

    def __str__(self):
        return f"{self.user.username} follows {self.project.title}"


# =========================================================
# PROJECT UPDATES
# =========================================================

class ProjectUpdate(models.Model):

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="updates"
    )

    title = models.CharField(
        max_length=200
    )

    content = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.project.title} - {self.title}"


# =========================================================
# PROJECT COLLABORATORS
# =========================================================

class ProjectCollaborator(models.Model):

    ROLE_CHOICES = [
        ("interested", "Interested"),
        ("frontend", "Frontend Developer"),
        ("backend", "Backend Developer"),
        ("fullstack", "Full Stack Developer"),
        ("designer", "UI/UX Designer"),
        ("tester", "Tester"),
        ("devops", "DevOps"),
        ("other", "Other"),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="collaborators"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="project_collaborations"
    )

    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default="interested"
    )
    STATUS_CHOICES = (('REQUESTED', 'Requested'), ('ACCEPTED', 'Accepted'), ('REJECTED', 'Rejected'))
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='REQUESTED', db_index=True)
    request_message = models.CharField(max_length=500, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    joined_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('project', 'user'),
                name='unique_project_collaborator',
            ),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.project.title}"


# =========================================================
# PROJECT REPORTS
# =========================================================

class ProjectReport(models.Model):

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="reports"
    )

    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="project_reports"
    )

    reason = models.CharField(
        max_length=100
    )

    description = models.TextField(
        blank=True
    )
    status = models.CharField(max_length=12, choices=(('OPEN', 'Open'), ('REVIEWED', 'Reviewed'), ('DISMISSED', 'Dismissed')), default='OPEN', db_index=True)
    moderator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderated_project_reports')
    moderation_note = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Report - {self.project.title}"


# =========================================================
# PROJECT SHARES
# =========================================================

class ProjectShare(models.Model):

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="shares"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_shares"
    )

    platform = models.CharField(
        max_length=30
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.project.title} - {self.platform}"


# =========================================================
# PROJECT VIEWS
# =========================================================

class ProjectView(models.Model):

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="views"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_views"
    )

    viewed_at = models.DateTimeField(
        auto_now_add=True
    )
    viewed_on = models.DateField(default=timezone.localdate)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('project', 'user', 'viewed_on'),
                condition=models.Q(user__isnull=False),
                name='unique_project_view_per_user_day',
            ),
        ]


class ProjectIdea(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_ideas')
    title = models.CharField(max_length=180)
    description = models.TextField(max_length=3000)
    tech_stack = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    upvoters = models.ManyToManyField(User, related_name='upvoted_project_ideas', blank=True)

    class Meta:
        ordering = ('-created_at',)


class AIRoadmap(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='ai_roadmap')
    content = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)


class AISavedContent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_ai_content')
    feature = models.CharField(max_length=32, db_index=True)
    content = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class AIUsage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_usage_records')
    feature = models.CharField(max_length=32, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    cached = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=('feature', 'created_at'), name='ai_usage_feature_date_idx')]

    def __str__(self):
        return f'{self.feature} usage by {self.user.username}'


# =========================================================
# PROJECT PRIVATE COMMUNICATION
# =========================================================

class Conversation(models.Model):
    STATUS_CHOICES = [
        ('ACCEPTED', 'Accepted'),
        ('REQUEST', 'Message request'),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="conversations",
        null=True,
        blank=True
    )

    project_owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="project_owner_conversations"
    )

    participant = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="project_participant_conversations"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='ACCEPTED',
    )
    request_sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_message_requests',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "project",
                    "project_owner",
                    "participant"
                ],
                name="unique_project_conversation"
            ),
            models.UniqueConstraint(
                fields=("project_owner", "participant"),
                condition=models.Q(project__isnull=True),
                name="unique_personal_conversation",
            ),
        ]

    def __str__(self):

        if self.project:

            return (
                f"{self.project.title} - "
                f"{self.participant.username}"
            )

        return (
            f"Chat - "
            f"{self.project_owner.username} / "
            f"{self.participant.username}"
        )


# =========================================================
# CHAT MESSAGE
# =========================================================

class Message(models.Model):

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages"
    )

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_project_messages"
    )

    content = models.TextField()

    is_delivered = models.BooleanField(
        default=False
    )

    is_read = models.BooleanField(
        default=False
    )

    deleted_for_everyone = models.BooleanField(
        default=False
    )
    edited_at = models.DateTimeField(null=True, blank=True)

    deleted_for_users = models.ManyToManyField(
        User,
        blank=True,
        related_name="deleted_messages"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=('conversation', 'created_at')),
        ]

    def __str__(self):

        return (
            f"{self.sender.username}: "
            f"{self.content[:40]}"
        )


# =========================================================
# MESSAGE ATTACHMENTS
# =========================================================

class MessageAttachment(models.Model):

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="attachments"
    )

    file = models.FileField(
        upload_to="message_attachment_upload_path",
        storage=PrivateMessageStorage(),
    )

    original_name = models.CharField(
        max_length=255
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return self.original_name


def message_attachment_upload_path(instance, filename):
    return f'message_attachments/{uuid.uuid4().hex}'


class ConversationPreference(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='conversation_preferences',
    )
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='user_preferences',
    )
    is_pinned = models.BooleanField(default=False)
    is_muted = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'conversation'),
                name='unique_user_conversation_preference',
            ),
        ]
        indexes = [models.Index(fields=('user', 'is_archived'))]


class MessageReaction(models.Model):
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='reactions',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='message_reactions',
    )
    emoji = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('message', 'user', 'emoji'),
                name='unique_message_user_emoji_reaction',
            ),
        ]


class MessageReport(models.Model):
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='reports',
    )
    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='message_reports',
    )
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('message', 'reporter'),
                name='unique_message_report_per_user',
            ),
        ]


# =========================================================
# CODING PRACTICE
# =========================================================

class PracticeProblem(models.Model):

    DIFFICULTY_CHOICES = [
        ('EASY', 'Easy'),
        ('MEDIUM', 'Medium'),
        ('HARD', 'Hard'),
    ]

    slug = models.SlugField(max_length=120, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES)
    category = models.CharField(max_length=40, default='python')
    tags = models.JSONField(default=list, blank=True)
    function_name = models.CharField(max_length=100)
    starter_code = models.JSONField(default=dict)
    example = models.JSONField(default=dict, blank=True)
    constraints = models.JSONField(default=list, blank=True)
    hints = models.JSONField(default=list, blank=True)
    editorial = models.TextField(blank=True)
    public_tests = models.JSONField(default=list)
    hidden_tests = models.JSONField(default=list)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.title


class PracticeProgress(models.Model):

    STATUS_CHOICES = [
        ('NOT_ATTEMPTED', 'Not attempted'),
        ('ATTEMPTED', 'Attempted'),
        ('SOLVED', 'Solved'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='practice_progress')
    problem = models.ForeignKey(PracticeProblem, on_delete=models.CASCADE, related_name='progress')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NOT_ATTEMPTED')
    attempt_count = models.PositiveIntegerField(default=0)
    last_submission = models.ForeignKey(
        'PracticeSubmission',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='latest_progress'
    )
    code_drafts = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    bookmarked = models.BooleanField(default=False)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    solved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'problem'),
                name='unique_practice_progress'
            )
        ]


class PracticeSubmission(models.Model):

    STATUS_CHOICES = [
        ('ACCEPTED', 'Accepted'),
        ('WRONG_ANSWER', 'Wrong answer'),
        ('COMPILATION_ERROR', 'Compilation error'),
        ('RUNTIME_ERROR', 'Runtime error'),
        ('TIME_LIMIT_EXCEEDED', 'Time limit exceeded'),
        ('INTERNAL_ERROR', 'Internal error'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='practice_submissions')
    problem = models.ForeignKey(PracticeProblem, on_delete=models.CASCADE, related_name='submissions')
    language = models.CharField(max_length=30)
    source_code = models.TextField()
    status = models.CharField(max_length=30, choices=STATUS_CHOICES)
    passed_test_cases = models.PositiveIntegerField(default=0)
    total_test_cases = models.PositiveIntegerField(default=0)
    execution_time = models.PositiveIntegerField(null=True, blank=True)
    memory_used = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    result_data = models.JSONField(default=dict, blank=True)
    # Browser-verified results are learner feedback, not trusted official scores.
    client_verified = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']


class PlaygroundSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='playground_sessions')
    title = models.CharField(max_length=120, default='Untitled session')
    language = models.CharField(max_length=30)
    source_code = models.TextField(blank=True)
    stdin = models.TextField(blank=True)
    share_token = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['user', '-updated_at'])]

    def __str__(self):
        return f'{self.title} ({self.user})'


class PracticeProblemSet(models.Model):
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    description = models.TextField(blank=True)
    problems = models.ManyToManyField(PracticeProblem, related_name='problem_sets', blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title


class MockTest(models.Model):
    DIFFICULTY_CHOICES = PracticeProblem.DIFFICULTY_CHOICES

    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    description = models.TextField(blank=True)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='EASY')
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    allow_retakes = models.BooleanField(default=True)
    active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['difficulty', 'title']

    def __str__(self):
        return self.title


class MockTestQuestion(models.Model):
    test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='questions')
    prompt = models.TextField()
    options = models.JSONField(default=list, blank=True)
    correct_answer = models.JSONField()
    explanation = models.TextField(blank=True)
    topic = models.CharField(max_length=80, blank=True)
    points = models.PositiveSmallIntegerField(default=1)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        indexes = [models.Index(fields=['test', 'order'])]

    def __str__(self):
        return f'{self.test}: question {self.order}'


class MockTestAttempt(models.Model):
    STATUS_CHOICES = [
        ('IN_PROGRESS', 'In progress'),
        ('SUBMITTED', 'Submitted'),
        ('COMPLETED', 'Completed'),
        ('EXPIRED', 'Expired'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mock_test_attempts')
    test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='attempts')
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    answers = models.JSONField(default=dict, blank=True)
    score = models.PositiveIntegerField(default=0)
    total_score = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_PROGRESS')

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['test', 'status']),
            models.Index(fields=['expires_at', 'status']),
        ]

    def __str__(self):
        return f'{self.user} - {self.test} ({self.status})'


# =========================================================
# USER FOLLOW REQUESTS
# =========================================================

class FollowRequest(models.Model):

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("ACCEPTED", "Accepted"),
        ("REJECTED", "Rejected"),
    ]

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_follow_requests"
    )

    receiver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_follow_requests"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING"
    )
    is_muted = models.BooleanField(default=False)

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=["sender", "receiver"],
                name="unique_follow_request"
            ),
            models.CheckConstraint(
                condition=~models.Q(
                    sender=models.F("receiver")
                ),
                name="prevent_self_follow_request"
            ),
        ]

        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.sender.username} → "
            f"{self.receiver.username} "
            f"({self.status})"
        )
        
# =========================================================
# USER BLOCKS
# =========================================================

class UserBlock(models.Model):

    blocker = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="blocks_created",
    )

    blocked = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="blocks_received",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["blocker", "blocked"],
                name="unique_user_block",
            ),
            models.CheckConstraint(
                condition=~models.Q(blocker=models.F("blocked")),
                name="prevent_self_block",
            ),
        ]


# =========================================================
# NOTIFICATIONS
# =========================================================

class Notification(models.Model):

    NOTIFICATION_TYPES = [
        ("FOLLOW_REQUEST", "Follow Request"),
        ("FOLLOW_ACCEPTED", "Follow Accepted"),
        ("FOLLOW_REJECTED", "Follow Rejected"),
        ("FOLLOW_BACK", "Follow Back"),
        ("COMMUNITY_REPLY", "Community Reply"),
        ("ASSIGNMENT_NEW", "New assignment"),
        ("ASSIGNMENT_DUE", "Assignment due soon"),
        ("ASSIGNMENT_EVALUATED", "Assignment evaluated"),
        ("COLLABORATOR_REQUEST", "Project collaboration request"),
        ("COLLABORATOR_RESPONSE", "Project collaboration update"),
        ("COMMUNITY_MENTION", "Community mention"),
        ("COMMUNITY_ACCEPTED", "Accepted answer"),
        ("NEW_FOLLOWER", "New Follower"),
        ("MESSAGE_REQUEST", "Message Request"),
        ("DAILY_LEADER", "Daily Leader"),
        ("LEVEL_UP", "Level Up"),
        ("PAYMENT_SUCCESS", "Payment successful"),
    ]

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_notifications"
    )

    community_post = models.ForeignKey(
        CommunityPost,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )

    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPES
    )

    message = models.CharField(
        max_length=255
    )

    dedupe_key = models.CharField(max_length=100, blank=True, default='')

    is_read = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=('recipient', 'is_read')),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=('recipient', 'notification_type', 'dedupe_key'),
                condition=~models.Q(dedupe_key=''),
                name='unique_notification_dedupe_key',
            ),
        ]


class XPEvent(models.Model):
    EVENT_CHOICES = [
        ('LESSON_DONE', 'Lesson completed'),
        ('FIRST_PROBLEM_SOLVE', 'First problem solved'),
        ('ASSIGNMENT_SUBMITTED', 'Assignment submitted'),
        ('ASSIGNMENT_EVALUATED', 'Assignment evaluated'),
        ('MOCK_TEST', 'Mock test completed'),
        ('DAILY_LOGIN', 'Daily login'),
        ('DAILY_MISSION', 'Daily mission completed'),
        ('MODULE_QUIZ', 'Module quiz passed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='xp_events')
    event_type = models.CharField(max_length=32, choices=EVENT_CHOICES)
    source_type = models.CharField(max_length=40)
    source_id = models.CharField(max_length=100)
    points = models.PositiveIntegerField(default=0)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'event_type', 'source_type', 'source_id'),
                name='unique_user_xp_source_event',
            ),
        ]
        indexes = [models.Index(fields=('user', 'created_at'))]


class StreakFreeze(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='streak_freezes')
    week_start = models.DateField()
    freeze_date = models.DateField(null=True, blank=True)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('user', 'week_start'), name='unique_weekly_streak_freeze'),
        ]


class DailyTopPerformer(models.Model):
    date = models.DateField(unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='daily_leader_wins')
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='daily_leader_wins')
    submission = models.ForeignKey(AssignmentSubmission, on_delete=models.CASCADE, related_name='daily_leader_awards')
    score = models.PositiveIntegerField(default=0)
    percent = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-date',)


class AITutorConversation(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ai_tutor_conversations",
    )
    title = models.CharField(max_length=120)
    pinned = models.BooleanField(default=False)
    summary = models.TextField(blank=True)
    share_token = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_active_at = models.DateTimeField()

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user.username}: {self.title}"


class AITutorMessage(models.Model):

    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
    ]

    conversation = models.ForeignKey(
        AITutorConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    feedback_rating = models.SmallIntegerField(null=True, blank=True)
    feedback_reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "id"]),
        ]

    def __str__(self):
        return (
            f"{self.sender.username} → "
            f"{self.recipient.username}: "
            f"{self.notification_type}"
        )