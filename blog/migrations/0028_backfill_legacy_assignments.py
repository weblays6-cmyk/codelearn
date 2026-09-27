from django.db import migrations


def publish_legacy_assignments(apps, schema_editor):
    Assignment = apps.get_model('blog', 'Assignment')
    Assignment.objects.filter(status='DRAFT').update(status='PUBLISHED')


class Migration(migrations.Migration):
    dependencies = [
        ('blog', '0027_assignment_assignment_source_and_more'),
    ]

    operations = [
        migrations.RunPython(publish_legacy_assignments, migrations.RunPython.noop),
    ]
