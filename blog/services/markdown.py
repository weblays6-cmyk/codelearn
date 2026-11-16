import html
import re

from django.utils.safestring import mark_safe


def render_lesson_markdown(source):
    blocks = re.split(r'```([^\n]*)\n(.*?)```', source or '', flags=re.DOTALL)
    rendered = []
    for index, block in enumerate(blocks):
        if index % 3 == 2:
            rendered.append(
                '<div class="lesson-code-block">'
                '<button type="button" class="copy-code" data-copy-code>Copy</button>'
                f'<pre><code>{html.escape(block.rstrip())}</code></pre></div>'
            )
            continue
        if index % 3 == 1:
            continue
        for line in block.splitlines():
            escaped = html.escape(line)
            escaped = re.sub(r'`([^`]+)`', r'<code>\1</code>', escaped)
            escaped = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', escaped)
            if escaped.startswith('### '):
                rendered.append(f'<h3>{escaped[4:]}</h3>')
            elif escaped.startswith('## '):
                rendered.append(f'<h2>{escaped[3:]}</h2>')
            elif escaped.startswith('# '):
                rendered.append(f'<h2>{escaped[2:]}</h2>')
            elif escaped.startswith('- '):
                rendered.append(f'<p class="lesson-list-item">{escaped[2:]}</p>')
            elif escaped:
                rendered.append(f'<p>{escaped}</p>')
    return mark_safe(''.join(rendered))
