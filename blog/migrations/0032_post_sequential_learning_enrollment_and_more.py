from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0031_module_lesson_module'),
    ]

    operations = [
        migrations.AddField(
            model_name='post',
            name='sequential_learning',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='enrollment',
            name='completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='enrollment',
            name='last_accessed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='enrollment',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='enrollment',
            name='status',
            field=models.CharField(
                choices=[
                    ('ENROLLED', 'Enrolled'),
                    ('IN_PROGRESS', 'In progress'),
                    ('COMPLETED', 'Completed'),
                ],
                default='ENROLLED',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='lessonprogress',
            name='last_accessed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='lessonprogress',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
