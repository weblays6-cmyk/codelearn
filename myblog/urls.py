from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('admin/', admin.site.urls),

    path(
        'accounts/3rdparty/login/cancelled/',
        RedirectView.as_view(pattern_name='blog:login'),
        name='branded_social_login_cancelled',
    ),
    path(
        'accounts/signup/',
        RedirectView.as_view(pattern_name='blog:signup'),
        name='branded_account_signup',
    ),

    # Google Login / Allauth
    path('accounts/', include('allauth.urls')),

    # CodeLearn Hub
    path('', include('blog.urls', namespace='blog')),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )