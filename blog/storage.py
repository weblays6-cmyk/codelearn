from django.conf import settings
from django.contrib.staticfiles.storage import StaticFilesStorage


class VersionedStaticFilesStorage(StaticFilesStorage):
    def url(self, name):
        url = super().url(name)
        separator = '&' if '?' in url else '?'
        return f'{url}{separator}v={settings.STATIC_BUILD_ID}'