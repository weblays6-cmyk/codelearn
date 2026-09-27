from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0029_practiceproblem_practicesubmission_practiceprogress'),
    ]

    operations = [
        migrations.AddField(
            model_name='post',
            name='status',
            field=models.CharField(
                choices=[
                    ('DRAFT', 'Draft'),
                    ('PUBLISHED', 'Published'),
                    ('ARCHIVED', 'Archived'),
                ],
                default='PUBLISHED',
                max_length=20,
            ),
        ),
    ]
