from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from blog.models import PracticeProblem, PracticeProblemSet


TOPICS = {
    'python': (
        ('Two Sum', 'Find the two indices whose values add to the target.', 'two_sum', 'Array'),
        ('Reverse a String', 'Return a string with its characters in reverse order.', 'reverse_string', 'String'),
        ('Palindrome Check', 'Check whether a string reads the same in both directions.', 'palindrome_check', 'String'),
        ('Fizz Buzz', 'Return labels for the integers from one through n.', 'fizzbuzz', 'Loops'),
        ('Valid Parentheses', 'Check whether every opening bracket is correctly closed.', 'is_valid', 'Stack'),
        ('Merge Sorted Lists', 'Merge two sorted arrays into one sorted array.', 'merge_sorted', 'Array'),
    ),
    'javascript': (
        ('Count Vowels', 'Count the vowels in a string without counting letter case.', 'count_vowels', 'String'),
        ('Flatten One Level', 'Flatten a nested array by exactly one level.', 'flatten_once', 'Array'),
        ('Unique Values', 'Return array values once, keeping their original order.', 'unique_values', 'Set'),
        ('Group by Key', 'Group objects by the requested property.', 'group_by_key', 'Objects'),
        ('Clamp Delay', 'Clamp a requested debounce delay to the supported 0–1000 ms range.', 'clamp_delay', 'Functions'),
        ('Preserve Input Order', 'Return input values in their original order.', 'preserve_order', 'Arrays'),
    ),
    'sql': (
        ('Filter Active Users', 'Select active users ordered by their display name.', 'filter_active_users', 'SELECT'),
        ('Count by Category', 'Count records in every category, including only non-empty groups.', 'count_by_category', 'GROUP BY'),
        ('Top Customers', 'Find the customers with the greatest total order value.', 'top_customers', 'JOIN'),
        ('Monthly Revenue', 'Aggregate completed order totals by calendar month.', 'monthly_revenue', 'Dates'),
        ('Duplicate Emails', 'Find normalized email addresses used by multiple accounts.', 'duplicate_emails', 'HAVING'),
        ('Update Inventory', 'Decrease inventory safely only when sufficient stock exists.', 'update_inventory', 'UPDATE'),
    ),
    'html-css': (
        ('Accessible Form', 'Build a labelled form with accessible required-field feedback.', 'accessible_form', 'Accessibility'),
        ('Responsive Card', 'Create a responsive information card using semantic HTML.', 'responsive_card', 'Responsive'),
        ('Flex Navigation', 'Arrange a navigation bar that wraps cleanly on narrow screens.', 'flex_navigation', 'Flexbox'),
        ('Grid Gallery', 'Build an image gallery with a responsive CSS grid.', 'grid_gallery', 'Grid'),
        ('Focus States', 'Add visible keyboard focus states to interactive controls.', 'focus_states', 'Accessibility'),
        ('CSS Variables', 'Create a small theme using reusable CSS custom properties.', 'css_variables', 'CSS'),
    ),
    'django': (
        ('Scoped Queryset', 'Return only published records visible to the current user.', 'scoped_queryset', 'Security'),
        ('Validated Form', 'Validate bounded user input in a Django form.', 'validated_form', 'Forms'),
        ('Safe Detail View', 'Fetch an object through a user-scoped queryset.', 'safe_detail_view', 'Views'),
        ('Atomic Transfer', 'Update two related balances in a single transaction.', 'atomic_transfer', 'Transactions'),
        ('Efficient Listing', 'Load related objects efficiently for a paginated listing.', 'efficient_listing', 'ORM'),
        ('CSRF Protected Action', 'Handle a state-changing form with method and CSRF protection.', 'csrf_action', 'Security'),
    ),
}

SQL_STARTERS = {
    'filter_active_users': 'SELECT display_name FROM users WHERE active = 1 ORDER BY display_name;\n',
    'count_by_category': 'SELECT category, COUNT(*) FROM products GROUP BY category ORDER BY category;\n',
    'top_customers': 'SELECT c.name, SUM(o.total) AS total FROM customers c JOIN orders o ON o.customer_id = c.id GROUP BY c.id ORDER BY total DESC LIMIT 2;\n',
    'monthly_revenue': "SELECT substr(order_date, 1, 7), SUM(total) FROM orders WHERE status = 'completed' GROUP BY substr(order_date, 1, 7) ORDER BY 1;\n",
    'duplicate_emails': 'SELECT lower(trim(email)) FROM accounts GROUP BY lower(trim(email)) HAVING COUNT(*) > 1 ORDER BY 1;\n',
    'update_inventory': 'UPDATE inventory SET quantity = quantity - 1 WHERE id = 1 AND quantity >= 1; SELECT id, quantity FROM inventory ORDER BY id;\n',
}

SQL_CASES = {
    'filter_active_users': [
        ("CREATE TABLE users(display_name TEXT, active INTEGER); INSERT INTO users VALUES ('Ada',1),('Grace',0),('Linus',1);", [['Ada'], ['Linus']]),
        ("CREATE TABLE users(display_name TEXT, active INTEGER); INSERT INTO users VALUES ('Zoe',1),('Amy',1),('Noor',0);", [['Amy'], ['Zoe']]),
        ("CREATE TABLE users(display_name TEXT, active INTEGER); INSERT INTO users VALUES ('Inactive',0);", []),
        ("CREATE TABLE users(display_name TEXT, active INTEGER); INSERT INTO users VALUES ('B',1),('A',1),('C',0);", [['A'], ['B']]),
        ("CREATE TABLE users(display_name TEXT, active INTEGER); INSERT INTO users VALUES ('Only',1);", [['Only']]),
        ("CREATE TABLE users(display_name TEXT, active INTEGER); INSERT INTO users VALUES ('Hidden',0),('Visible',1);", [['Visible']]),
    ],
    'count_by_category': [
        ("CREATE TABLE products(category TEXT); INSERT INTO products VALUES ('book'),('book'),('game');", [['book', 2], ['game', 1]]),
        ("CREATE TABLE products(category TEXT); INSERT INTO products VALUES ('a'),('b'),('b'),('b');", [['a', 1], ['b', 3]]),
        ("CREATE TABLE products(category TEXT); INSERT INTO products VALUES ('solo');", [['solo', 1]]),
        ("CREATE TABLE products(category TEXT); INSERT INTO products VALUES ('x'),('x'),('y'),('z'),('z');", [['x', 2], ['y', 1], ['z', 2]]),
        ("CREATE TABLE products(category TEXT); INSERT INTO products VALUES ('single'),('single');", [['single', 2]]),
        ("CREATE TABLE products(category TEXT); INSERT INTO products VALUES ('h'),('h'),('i');", [['h', 2], ['i', 1]]),
    ],
    'top_customers': [
        ("CREATE TABLE customers(id INTEGER, name TEXT); CREATE TABLE orders(customer_id INTEGER, total REAL); INSERT INTO customers VALUES (1,'Ada'),(2,'Lin'); INSERT INTO orders VALUES (1,10),(2,20),(1,5);", [['Lin', 20], ['Ada', 15]]),
        ("CREATE TABLE customers(id INTEGER, name TEXT); CREATE TABLE orders(customer_id INTEGER, total REAL); INSERT INTO customers VALUES (1,'A'),(2,'B'); INSERT INTO orders VALUES (1,2),(2,9);", [['B', 9], ['A', 2]]),
        ("CREATE TABLE customers(id INTEGER, name TEXT); CREATE TABLE orders(customer_id INTEGER, total REAL); INSERT INTO customers VALUES (1,'A'); INSERT INTO orders VALUES (1,0);", [['A', 0]]),
        ("CREATE TABLE customers(id INTEGER, name TEXT); CREATE TABLE orders(customer_id INTEGER, total REAL); INSERT INTO customers VALUES (1,'A'),(2,'B'),(3,'C'); INSERT INTO orders VALUES (1,4),(2,7),(3,3);", [['B', 7], ['A', 4]]),
        ("CREATE TABLE customers(id INTEGER, name TEXT); CREATE TABLE orders(customer_id INTEGER, total REAL); INSERT INTO customers VALUES (1,'A'); INSERT INTO orders VALUES (1,11);", [['A', 11]]),
        ("CREATE TABLE customers(id INTEGER, name TEXT); CREATE TABLE orders(customer_id INTEGER, total REAL); INSERT INTO customers VALUES (1,'A'),(2,'B'); INSERT INTO orders VALUES (1,6),(2,8);", [['B', 8], ['A', 6]]),
    ],
    'monthly_revenue': [
        ("CREATE TABLE orders(order_date TEXT, status TEXT, total REAL); INSERT INTO orders VALUES ('2026-01-03','completed',10),('2026-01-20','completed',5),('2026-02-01','pending',100);", [['2026-01', 15]]),
        ("CREATE TABLE orders(order_date TEXT, status TEXT, total REAL); INSERT INTO orders VALUES ('2026-03-01','completed',8),('2026-04-01','completed',2);", [['2026-03', 8], ['2026-04', 2]]),
        ("CREATE TABLE orders(order_date TEXT, status TEXT, total REAL); INSERT INTO orders VALUES ('2026-05-01','pending',7);", []),
        ("CREATE TABLE orders(order_date TEXT, status TEXT, total REAL); INSERT INTO orders VALUES ('2026-06-01','completed',1),('2026-06-02','completed',9);", [['2026-06', 10]]),
        ("CREATE TABLE orders(order_date TEXT, status TEXT, total REAL); INSERT INTO orders VALUES ('2026-07-01','completed',0);", [['2026-07', 0]]),
        ("CREATE TABLE orders(order_date TEXT, status TEXT, total REAL); INSERT INTO orders VALUES ('2026-08-01','completed',4),('2026-09-01','completed',3);", [['2026-08', 4], ['2026-09', 3]]),
    ],
    'duplicate_emails': [
        ("CREATE TABLE accounts(email TEXT); INSERT INTO accounts VALUES (' ADA@example.com '),('ada@example.com'),('grace@example.com');", [['ada@example.com']]),
        ("CREATE TABLE accounts(email TEXT); INSERT INTO accounts VALUES ('x@x.com'),('X@X.COM'),('y@y.com');", [['x@x.com']]),
        ("CREATE TABLE accounts(email TEXT); INSERT INTO accounts VALUES ('solo@x.com');", []),
        ("CREATE TABLE accounts(email TEXT); INSERT INTO accounts VALUES ('a@x.com'),('a@x.com'),('b@x.com'),('B@X.COM');", [['a@x.com'], ['b@x.com']]),
        ("CREATE TABLE accounts(email TEXT); INSERT INTO accounts VALUES ('n@x.com'),(' N@X.COM ');", [['n@x.com']]),
        ("CREATE TABLE accounts(email TEXT); INSERT INTO accounts VALUES ('first@x.com'),('FIRST@X.COM'),('other@x.com');", [['first@x.com']]),
    ],
    'update_inventory': [
        ("CREATE TABLE inventory(id INTEGER, quantity INTEGER); INSERT INTO inventory VALUES (1,3),(2,0);", [[1, 2], [2, 0]]),
        ("CREATE TABLE inventory(id INTEGER, quantity INTEGER); INSERT INTO inventory VALUES (1,1),(2,5);", [[1, 0], [2, 5]]),
        ("CREATE TABLE inventory(id INTEGER, quantity INTEGER); INSERT INTO inventory VALUES (1,0);", [[1, 0]]),
        ("CREATE TABLE inventory(id INTEGER, quantity INTEGER); INSERT INTO inventory VALUES (1,10),(2,2);", [[1, 9], [2, 2]]),
        ("CREATE TABLE inventory(id INTEGER, quantity INTEGER); INSERT INTO inventory VALUES (1,2);", [[1, 1]]),
        ("CREATE TABLE inventory(id INTEGER, quantity INTEGER); INSERT INTO inventory VALUES (1,0),(2,4);", [[1, 0], [2, 4]]),
    ],
}

FUNCTION_CASES = {
    'two_sum': [
        ([[2, 7, 11, 15], 9], [0, 1]), ([[3, 2, 4], 6], [1, 2]), ([[3, 3], 6], [0, 1]),
        ([[1, 2, 3, 4, 5], 9], [3, 4]), ([[0, 4, 3, 0], 0], [0, 3]), ([[-1, 4, 2], 1], [0, 1]),
    ],
    'reverse_string': [
        (['code'], 'edoc'), ([''], ''), (['level'], 'level'),
        (['abcde'], 'edcba'), (['a b'], 'b a'), (['123'], '321'),
    ],
    'is_palindrome': [
        (['level'], True), (['code'], False), ([''], True),
        (['Never odd or even'.replace(' ', '').lower()], True), (['a'], True), (['ab'], False),
    ],
    'fizz_buzz': [
        ([5], ['1', '2', 'Fizz', '4', 'Buzz']), ([3], ['1', '2', 'Fizz']), ([1], ['1']),
        ([15], ['1', '2', 'Fizz', '4', 'Buzz', 'Fizz', '7', '8', 'Fizz', 'Buzz', '11', 'Fizz', '13', '14', 'FizzBuzz']),
        ([0], []), ([6], ['1', '2', 'Fizz', '4', 'Buzz', 'Fizz']),
    ],
    'is_valid': [
        (['()[]{}'], True), (['(]'], False), ([''], True),
        (['((()))'], True), (['([)]'], False), (['{[]}'], True),
    ],
    'merge_sorted': [
        ([[1, 3], [2, 4]], [1, 2, 3, 4]), ([[], [1]], [1]), ([[1], []], [1]),
        ([[-3, 1], [-2, 2]], [-3, -2, 1, 2]), ([[1, 1], [1]], [1, 1, 1]), ([[0], [0]], [0, 0]),
    ],
    'count_vowels': [
        (['Hello'], 2), (['rhythm'], 0), (['AEIOU'], 5),
        (['World!'], 1), ([''], 0), (['Education'], 5),
    ],
    'flatten_once': [
        ([[1, [2], [3, [4]]]], [1, 2, 3, [4]]), ([[]], []), ([[1, 2]], [1, 2]),
        ([[[1]], [[2]]], [[1], [2]]), ([[0, [1, [2]]]], [0, 1, [2]]), ([[['x']]], [['x']]),
    ],
    'unique_values': [
        ([[1, 2, 1, 3]], [1, 2, 3]), ([[]], []), ([[1, 1]], [1]),
        ([['a', 'b', 'a']], ['a', 'b']), ([[3, 2, 3, 1]], [3, 2, 1]), ([[False, True, False]], [False, True]),
    ],
    'group_by_key': [
        ([[{'team': 'a', 'name': 'A'}, {'team': 'b', 'name': 'B'}, {'team': 'a', 'name': 'C'}], 'team'], {'a': [{'team': 'a', 'name': 'A'}, {'team': 'a', 'name': 'C'}], 'b': [{'team': 'b', 'name': 'B'}]}),
        ([[], 'team'], {}), ([[{'team': 'x'}], 'team'], {'x': [{'team': 'x'}]}),
        ([[{'k': 1}, {'k': 1}, {'k': 2}], 'k'], {'1': [{'k': 1}, {'k': 1}], '2': [{'k': 2}]}),
        ([[{'team': 'b'}, {'team': 'a'}], 'team'], {'b': [{'team': 'b'}], 'a': [{'team': 'a'}]}),
        ([[{'team': 'one'}], 'team'], {'one': [{'team': 'one'}]}),
    ],
    'clamp_delay': [([3], 3), ([0], 0), ([-5], 0), ([1200], 1000), ([25], 25), ([1001], 1000)],
    'preserve_order': [([[3, 1, 2]], [3, 1, 2]), ([[]], []), ([[1]], [1]), ([[4, 4]], [4, 4]), ([['a', 'b']], ['a', 'b']), ([[0, -1]], [0, -1])],
    'scoped_queryset': [
        ([[{'owner_id': 7, 'status': 'PUBLISHED', 'id': 1}, {'owner_id': 8, 'status': 'PUBLISHED', 'id': 2}, {'owner_id': 7, 'status': 'DRAFT', 'id': 3}], 7], [{'owner_id': 7, 'status': 'PUBLISHED', 'id': 1}]),
        ([[], 1], []), ([[{'owner_id': 1, 'status': 'PUBLISHED', 'id': 1}], 1], [{'owner_id': 1, 'status': 'PUBLISHED', 'id': 1}]),
        ([[{'owner_id': 2, 'status': 'PUBLISHED', 'id': 1}], 1], []), ([[{'owner_id': 1, 'status': 'DRAFT'}], 1], []), ([[{'owner_id': 3, 'status': 'PUBLISHED'}, {'owner_id': 3, 'status': 'PUBLISHED'}], 3], [{'owner_id': 3, 'status': 'PUBLISHED'}, {'owner_id': 3, 'status': 'PUBLISHED'}]),
    ],
    'validated_form': [(['hello'], True), ([''], False), (['x' * 101], False), (['a'], True), (['0'], True), ([' '], False)],
    'safe_detail_view': [
        ([[{'id': 1, 'owner': 2}, {'id': 2, 'owner': 1}], 2, 1], {'id': 2, 'owner': 1}),
        ([[], 1, 1], None), ([[{'id': 3, 'owner': 1}], 3, 2], None),
        ([[{'id': 4, 'owner': 4}], 4, 4], {'id': 4, 'owner': 4}), ([[{'id': 5, 'owner': 8}], 5, 8], {'id': 5, 'owner': 8}), ([[{'id': 1, 'owner': 1}], 9, 1], None),
    ],
    'atomic_transfer': [
        ([{'a': 10, 'b': 2}, 'a', 'b', 3], {'a': 7, 'b': 5}), ([{'a': 1, 'b': 0}, 'a', 'b', 2], None),
        ([{'a': 5, 'b': 1}, 'a', 'b', 0], {'a': 5, 'b': 1}), ([{'a': 9, 'b': 0}, 'a', 'b', 9], {'a': 0, 'b': 9}),
        ([{'a': 2, 'b': 4}, 'a', 'b', 3], None), ([{'a': 4, 'b': 1}, 'a', 'b', 1], {'a': 3, 'b': 2}),
    ],
    'efficient_listing': [
        ([[{'name': 'b', 'id': 1}, {'name': 'a', 'id': 2}],], [{'name': 'a', 'id': 2}, {'name': 'b', 'id': 1}]),
        ([[]], []), ([[{'name': 'x', 'id': 1}],], [{'name': 'x', 'id': 1}]),
        ([[{'name': 'z', 'id': 1}, {'name': 'm', 'id': 2}, {'name': 'a', 'id': 3}],], [{'name': 'a', 'id': 3}, {'name': 'm', 'id': 2}, {'name': 'z', 'id': 1}]),
        ([[{'name': 'same', 'id': 2}, {'name': 'same', 'id': 1}],], [{'name': 'same', 'id': 1}, {'name': 'same', 'id': 2}]),
        ([[{'name': 'one', 'id': 1}],], [{'name': 'one', 'id': 1}]),
    ],
    'csrf_action': [
        ([{'method': 'POST', 'csrf_valid': True}], True), ([{'method': 'GET', 'csrf_valid': False}], False),
        ([{'method': 'POST', 'csrf_valid': False}], False), ([{'method': 'DELETE', 'csrf_valid': True}], False),
        ([{'method': 'POST', 'csrf_valid': True}], True), ([{'method': 'GET', 'csrf_valid': True}], False),
    ],
}
FUNCTION_CASES['palindrome_check'] = FUNCTION_CASES['is_palindrome']
FUNCTION_CASES['fizzbuzz'] = FUNCTION_CASES['fizz_buzz']

HTML_CASES = {
    'accessible_form': [
        ('Every field has a visible label', 'visible labels'),
        ('Required fields are announced accessibly', 'required and described'),
        ('Validation messages are announced', 'aria-live feedback'),
        ('Keyboard focus is visible', 'visible focus style'),
        ('Labels remain associated after form changes', 'stable label association'),
        ('Invalid input receives a useful message', 'field-specific feedback'),
    ],
    'responsive_card': [
        ('Card uses a semantic container', 'semantic markup'),
        ('Card content fits a narrow viewport', 'no horizontal overflow'),
        ('Heading order is meaningful', 'logical headings'),
        ('Links have descriptive names', 'accessible link text'),
        ('Long content wraps safely', 'responsive text'),
        ('Spacing adapts to viewport width', 'responsive layout'),
    ],
    'flex_navigation': [
        ('Navigation uses a list of links', 'semantic navigation'),
        ('Links wrap on narrow screens', 'responsive flex-wrap'),
        ('Keyboard focus remains visible', 'visible focus'),
        ('Current page is identified', 'current-page state'),
        ('Link spacing stays usable', 'touch-friendly gaps'),
        ('Layout does not overflow', 'no horizontal scrolling'),
    ],
    'grid_gallery': [
        ('Gallery uses a responsive grid', 'CSS grid'),
        ('Images have useful alt text', 'descriptive alt'),
        ('Columns adapt to viewport width', 'responsive columns'),
        ('Images preserve their proportions', 'object-fit or aspect ratio'),
        ('Gallery items have consistent spacing', 'grid gap'),
        ('Small screens remain readable', 'mobile layout'),
    ],
    'focus_states': [
        ('Keyboard focus is visible', 'visible outline'),
        ('Focus is not indicated by color alone', 'non-color focus cue'),
        ('Interactive controls are reachable', 'keyboard access'),
        ('Focus indicator has sufficient contrast', 'contrast'),
        ('Hover styling does not replace focus', 'focus and hover'),
        ('Focus order follows the visual order', 'logical sequence'),
    ],
    'css_variables': [
        ('Theme values use custom properties', '--custom properties'),
        ('Colors are reused consistently', 'reusable tokens'),
        ('A fallback value is provided', 'fallback'),
        ('Theme changes preserve contrast', 'readable contrast'),
        ('Spacing values are centralized', 'shared spacing values'),
        ('Styles remain scoped to the component', 'scoped selectors'),
    ],
}


def starter_codes(language, function_name):
    parameters = {
        'two_sum': 'nums, target',
        'merge_sorted': 'left, right',
        'group_by_key': 'items, key',
        'scoped_queryset': 'records, user_id',
        'safe_detail_view': 'records, object_id, user_id',
        'atomic_transfer': 'balances, source, target, amount',
        'csrf_action': 'request',
    }.get(function_name, 'value')
    if language == 'python' or language == 'django':
        return {'python': f'def {function_name}({parameters}):\n    # Return the requested result\n    pass\n'}
    if language == 'javascript':
        return {'javascript': f'function {function_name}({parameters}) {{\n  // Return the requested result\n}}\n'}
    if language == 'sql':
        return {'sql': SQL_STARTERS[function_name]}
    return {'html': '<main>\n  <!-- Use semantic, accessible markup -->\n</main>\n'}


class Command(BaseCommand):
    help = 'Idempotently seed 30 practice problems and curated problem tracks.'

    @transaction.atomic
    def handle(self, *args, **options):
        problems = []
        index = 0
        for category, rows in TOPICS.items():
            for title, description, function_name, topic in rows:
                index += 1
                difficulty = ('EASY', 'MEDIUM', 'HARD')[(index - 1) % 3]
                sample_cases = [
                    {'input': [1, 2], 'expected': 3},
                    {'input': [0, 5], 'expected': 5},
                    {'input': [-2, 2], 'expected': 0},
                ]
                if category == 'sql':
                    sample_cases = [
                        {'input': {'setup': setup}, 'expected': expected}
                        for setup, expected in SQL_CASES[function_name][:3]
                    ]
                    hidden_cases = [
                        {'input': {'setup': setup}, 'expected': expected}
                        for setup, expected in SQL_CASES[function_name][3:]
                    ]
                    codes = starter_codes(category, function_name)
                    codes['sql'] = SQL_STARTERS[function_name]
                elif function_name in FUNCTION_CASES:
                    function_cases = FUNCTION_CASES[function_name]
                    sample_cases = [
                        {'input': input_value, 'expected': expected}
                        for input_value, expected in function_cases[:3]
                    ]
                    hidden_cases = [
                        {'input': input_value, 'expected': expected}
                        for input_value, expected in function_cases[3:]
                    ]
                    codes = starter_codes(category, function_name)
                elif category == 'html-css':
                    html_cases = HTML_CASES[function_name]
                    sample_cases = [
                        {'input': prompt, 'expected': expected}
                        for prompt, expected in html_cases[:3]
                    ]
                    hidden_cases = [
                        {'input': prompt, 'expected': expected}
                        for prompt, expected in html_cases[3:]
                    ]
                    codes = starter_codes(category, function_name)
                else:
                    hidden_cases = [
                        {'input': [10, 20], 'expected': 30},
                        {'input': [100, -1], 'expected': 99},
                        {'input': [7, 0], 'expected': 7},
                    ]
                    codes = starter_codes(category, function_name)
                slug = 'fizzbuzz' if title == 'Fizz Buzz' else slugify(title)
                defaults = {
                    'title': title,
                    'description': f'{description}\n\nTopic: {topic}. Consider empty input and boundary cases.',
                    'difficulty': difficulty,
                    'category': category,
                    'tags': [topic, category.replace('-', ' ').title()],
                    'function_name': function_name,
                    'starter_code': codes,
                    'example': {'input': '[1, 2]', 'output': '3'},
                    'constraints': ['Input is within the documented range.', 'Do not mutate shared global state.'],
                    'public_tests': sample_cases,
                    'hidden_tests': hidden_cases,
                    'hints': [
                        'Write down the expected output for the smallest input.',
                        'Choose a data structure that matches the lookup pattern.',
                        'Check how your solution handles empty or repeated values.',
                    ],
                    'editorial': f'Identify the input shape, apply a direct solution for {topic.lower()}, then verify normal, boundary, and repeated-value cases.',
                    'active': True,
                }
                problem, created = PracticeProblem.objects.get_or_create(
                    slug=slug,
                    defaults=defaults,
                )
                if not created:
                    missing = {
                        field: value
                        for field, value in defaults.items()
                        if getattr(problem, field) in (None, '', [], {})
                    }
                    if missing:
                        PracticeProblem.objects.filter(pk=problem.pk).update(**missing)
                        for field, value in missing.items():
                            setattr(problem, field, value)
                problems.append(problem)

        tracks = (
            ('Python 30 Days', 'python-30-days', 'A progressive Python practice path.', problems[0:6]),
            ('SQL Basics', 'sql-basics', 'Build confidence with practical SQL patterns.', problems[12:18]),
            ('Interview 50', 'interview-50', 'A cross-topic interview preparation track.', problems[:]),
        )
        for title, slug, description, members in tracks:
            problem_set, _ = PracticeProblemSet.objects.get_or_create(
                slug=slug,
                defaults={'title': title, 'description': description, 'active': True},
            )
            problem_set.problems.add(*members)
        self.stdout.write(self.style.SUCCESS('Seeded 30 practice problems and 3 curated problem sets.'))
