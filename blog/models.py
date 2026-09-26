from django.db import models
from django.contrib.auth.models import User


# =========================================================
# COURSE / POST
# =========================================================

class Post(models.Model):

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
# LESSON
# =========================================================

class Lesson(models.Model):

    course = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='lessons'
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
        related_name='assignments'
    )

    title = models.CharField(
        max_length=200
    )

    description = models.TextField()

    max_score = models.PositiveIntegerField(
        default=100
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.lesson.title} - {self.title}"


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