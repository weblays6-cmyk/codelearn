from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from blog.models import Lesson, Module, ModuleQuiz, Post, QuizQuestion


COURSES = (
    ('Python Fundamentals', 'Python', 'Beginner', 240, 'Build a strong foundation in Python, from values and control flow to reusable functions and small programs.', 'Variables and data types\nControl flow\nFunctions\nLists and dictionaries'),
    ('Django for Beginners', 'Django', 'Beginner', 300, 'Create maintainable web applications with Django models, views, URLs, templates, and forms.', 'Django project structure\nModels and migrations\nViews and URLs\nTemplates and forms'),
    ('SQL Essentials', 'SQL', 'Beginner', 180, 'Query and shape relational data with practical, standards-based SQL.', 'SELECT and filtering\nJoins\nAggregations\nSafe data changes'),
    ('JavaScript Basics', 'JavaScript', 'Beginner', 240, 'Learn the JavaScript language and browser fundamentals for interactive web experiences.', 'Values and functions\nArrays and objects\nDOM events\nAsync basics'),
    ('HTML & CSS', 'HTML/CSS', 'Beginner', 210, 'Build accessible, responsive web pages with semantic HTML and modern CSS.', 'Semantic markup\nAccessible forms\nCSS layout\nResponsive design'),
    ('Data Structures', 'Python', 'Intermediate', 300, 'Understand core data structures and choose the right tool for common programming problems.', 'Arrays and strings\nStacks and queues\nHash maps\nTrees and complexity'),
)

LESSON_TOPICS = (
    ('Core ideas', 'Read the example carefully and identify the data and steps involved.'),
    ('A worked example', 'Trace the example from input to output before changing it.'),
    ('Common mistakes', 'Check types, boundary cases, and the exact meaning of each operation.'),
    ('Practice and review', 'Make one small change, run it, and compare the result with your expectation.'),
)

QUESTIONS = (
    ('Which habit makes code easier to understand?', ['Use descriptive names', 'Hide behavior in long expressions', 'Repeat the same logic', 'Skip testing'], 0, 'Descriptive names explain intent and make code easier to review.'),
    ('What is a useful first debugging step?', ['Read the full error message', 'Change several things at once', 'Ignore the failing input', 'Delete the test'], 0, 'The error message and failing input usually identify where to investigate.'),
    ('Why should a program be split into small functions?', ['To isolate responsibilities', 'To make every function global', 'To avoid naming values', 'To remove tests'], 0, 'Small functions make behavior easier to reuse and verify.'),
    ('What should a test compare?', ['Actual behavior with expected behavior', 'Two unrelated values', 'Only the program name', 'Nothing after an error'], 0, 'A test checks observed behavior against a clear expectation.'),
    ('How should you handle an unfamiliar concept?', ['Build and verify a small example', 'Copy code without reading it', 'Assume all inputs are valid', 'Skip the documentation'], 0, 'A small example makes assumptions visible and provides quick feedback.'),
)


def _sample_code(category, title):
    samples = {
        'Python': 'def greet(name):\n    return f"Hello, {name}"\n\nprint(greet("Ada"))',
        'Django': 'from django.http import HttpResponse\n\n\ndef home(request):\n    return HttpResponse("Hello, Django!")',
        'SQL': 'SELECT name, created_at\nFROM learners\nWHERE active = TRUE\nORDER BY created_at DESC;',
        'JavaScript': 'const greet = (name) => `Hello, ${name}`;\n\nconsole.log(greet("Ada"));',
        'HTML/CSS': '<main class="card">\n  <h1>Welcome</h1>\n  <p>Build a clear page.</p>\n</main>',
    }
    return samples.get(category, 'items = [3, 1, 2]\nfor item in sorted(items):\n    print(item)')


class Command(BaseCommand):
    help = 'Create or complete the six introductory courses and their lessons and quizzes.'

    def add_arguments(self, parser):
        parser.add_argument('--username', help='User account to show as the course instructor.')

    @transaction.atomic
    def handle(self, *args, **options):
        user_model = get_user_model()
        username = options.get('username')
        if username:
            instructor = user_model.objects.filter(username=username, is_active=True).first()
        else:
            instructor = user_model.objects.filter(is_active=True, is_staff=True).order_by('pk').first()
            if instructor is None:
                instructor = user_model.objects.filter(is_active=True).order_by('pk').first()
        if instructor is None:
            raise CommandError('Create an active user before seeding courses or pass --username.')

        lesson_total = 0
        quiz_total = 0
        for title, category, difficulty, duration, description, learning in COURSES:
            slug = slugify(title)
            course, _ = Post.objects.get_or_create(
                slug=slug,
                defaults={
                    'title': title,
                    'category': category,
                    'difficulty': difficulty,
                    'duration_minutes': duration,
                    'description': description,
                    'what_you_learn': learning,
                    'prerequisites': 'No prior experience required.' if difficulty == 'Beginner' else 'Comfort with basic programming concepts.',
                    'content': description,
                    'author': instructor,
                    'status': 'PUBLISHED',
                    'is_free': True,
                    'price': 0,
                },
            )
            modules = (
                (f'{title}: Foundations', 'Learn the vocabulary and core building blocks.'),
                (f'{title}: Practical skills', 'Apply the fundamentals in small, verifiable steps.'),
            )
            for module_order, (module_title, module_description) in enumerate(modules, 1):
                module, _ = Module.objects.get_or_create(
                    course=course,
                    order=module_order,
                    defaults={'title': module_title, 'description': module_description},
                )
                quiz, _ = ModuleQuiz.objects.get_or_create(
                    module=module,
                    defaults={'title': f'{module_title} quiz', 'passing_score': 70},
                )
                quiz_total += 1
                for question_order, (prompt, choices, correct, explanation) in enumerate(QUESTIONS, 1):
                    QuizQuestion.objects.get_or_create(
                        quiz=quiz,
                        order=question_order,
                        defaults={
                            'prompt': f'{prompt} ({module_title})',
                            'options': choices,
                            'correct_option': correct,
                            'explanation': explanation,
                        },
                    )
                for lesson_order, (lesson_title, explanation) in enumerate(LESSON_TOPICS, 1):
                    complete_title = f'{module_title}: {lesson_title}'
                    lesson_slug = slugify(complete_title)[:220]
                    content = (
                        f'# {lesson_title}\n\n{explanation}\n\n'
                        f'## Example\n\n```{category.lower()}\n'
                        f'{_sample_code(category, complete_title)}\n```\n\n'
                        'Change one line, predict the result, and run the example again.\n'
                    )
                    Lesson.objects.get_or_create(
                        slug=lesson_slug,
                        defaults={
                            'course': course,
                            'module': module,
                            'title': lesson_title,
                            'content': content,
                            'order': module_order * 10 + lesson_order,
                        },
                    )
                    lesson_total += 1
        self.stdout.write(self.style.SUCCESS(
            f'Seeded 6 courses; verified 12 module quizzes and {lesson_total} lesson records.'
        ))
