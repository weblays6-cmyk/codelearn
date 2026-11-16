from django.conf import settings
from django.db import migrations


def update_site_brand(apps, schema_editor):
    Site = apps.get_model('sites', 'Site')
    sites = Site.objects.using(schema_editor.connection.alias)
    site = sites.filter(pk=settings.SITE_ID).first()
    if site is None:
        return

    site.name = 'vGrowHub'
    target_domain = 'vgrowhub.hopto.org'
    domain_owner = sites.filter(domain=target_domain).first()
    if domain_owner is not None and domain_owner.pk != site.pk:
        domain_owner.name = 'vGrowHub'
        domain_owner.save(update_fields=['name'])
    else:
        site.domain = target_domain

    site.save(update_fields=['name', 'domain'])


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0067_alter_enrollment_certificate_code'),
        ('sites', '0002_alter_domain_unique'),
    ]

    operations = [
        migrations.RunPython(update_site_brand, migrations.RunPython.noop),
    ]
