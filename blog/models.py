from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


# =========================================================
# COURSE / POST
# =========================================================

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

    title = models.CharField(
        max_length=100
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

    what_you_learn = models.TextField(
        blank=True
    )

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

    content = models.TextField()

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
    required = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_assignments')
    published_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def clean(self):
        errors = {}

        if self.assignment_source == 'COURSE' and not self.course and not self.lesson:
            errors['course'] = 'Course assignments must be linked to a course or lesson.'

        if self.assignment_source == 'STANDALONE' and (self.course or self.lesson):
            errors['assignment_source'] = 'Standalone assignments cannot be linked to a course or lesson.'

        if self.course and self.lesson and self.lesson.course_id != self.course_id:
            errors['lesson'] = 'The selected lesson must belong to the selected course.'

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


# =========================================================
# USER PROFILE
# =========================================================

class UserProfile(models.Model):

    GOAL_CHOICES = [
        (
            'job',
            'Get a Job'
        ),
        (
            'skill',
            'Learn a New Skill'
        ),
        (
            'projects',
            'Build Projects'
        ),
        (
            'interview',
            'Prepare for Interviews'
        ),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile_data'
    )

    goal = models.CharField(
        max_length=20,
        choices=GOAL_CHOICES,
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.user.username


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


# =========================================================
# DEVELOPER PROJECT
# =========================================================

class Project(models.Model):

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

    joined_at = models.DateTimeField(
        auto_now_add=True
    )

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

    def __str__(self):
        return f"{self.project.title} view"


# =========================================================
# PROJECT PRIVATE COMMUNICATION
# =========================================================

class Conversation(models.Model):

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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "project",
                    "project_owner",
                    "participant"
                ],
                name="unique_project_conversation"
            )
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
        upload_to="message_attachments/"
    )

    original_name = models.CharField(
        max_length=255
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return self.original_name


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
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']


class PlaygroundSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='playground_sessions')
    title = models.CharField(max_length=120, default='Untitled session')
    language = models.CharField(max_length=30)
    source_code = models.TextField(blank=True)
    stdin = models.TextField(blank=True)
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
# NOTIFICATIONS
# =========================================================

class Notification(models.Model):

    NOTIFICATION_TYPES = [
        ("FOLLOW_REQUEST", "Follow Request"),
        ("FOLLOW_ACCEPTED", "Follow Accepted"),
        ("FOLLOW_REJECTED", "Follow Rejected"),
        ("FOLLOW_BACK", "Follow Back"),
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

    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPES
    )

    message = models.CharField(
        max_length=255
    )

    is_read = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.sender.username} → "
            f"{self.recipient.username}: "
            f"{self.notification_type}"
        )