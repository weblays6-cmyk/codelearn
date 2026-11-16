from django.db import migrations, models

from blog.migration_ops import EnsureNullableUniqueField


class Migration(migrations.Migration):
    dependencies = [
        ('blog', '0065_alter_notification_notification_type_payment'),
    ]

    operations = [
        EnsureNullableUniqueField(
            'enrollment',
            'certificate_code',
            models.CharField(
                blank=True,
                default=None,
                editable=False,
                max_length=36,
                null=True,
                unique=True,
            ),
        ),
    ]