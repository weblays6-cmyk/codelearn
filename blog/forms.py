from pathlib import Path

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from .models import (
    Post,
    Comment,
    UserProfile,
    Project,
    CommunityPost,
    CommunityReply,
)

PROFILE_PICTURE_MAX_SIZE = 5 * 1024 * 1024
PROFILE_PICTURE_FORMATS = {
    '.jpg': 'JPEG',
    '.jpeg': 'JPEG',
    '.png': 'PNG',
    '.webp': 'WEBP',
}


def validate_profile_picture(profile_picture):
    if not profile_picture:
        return profile_picture

    if profile_picture.size > PROFILE_PICTURE_MAX_SIZE:
        raise ValidationError('Profile pictures must be 5 MB or smaller.')

    extension = Path(profile_picture.name).suffix.lower()
    expected_format = PROFILE_PICTURE_FORMATS.get(extension)
    actual_format = getattr(getattr(profile_picture, 'image', None), 'format', None)
    if not expected_format or actual_format != expected_format:
        raise ValidationError('Choose a valid JPG, PNG, or WEBP image.')
    image = profile_picture.image
    if image.width != image.height:
        raise ValidationError('Crop profile pictures to a square before saving.')

    return profile_picture


class PostForm(forms.ModelForm):

    class Meta:
        model = Post

        fields = [
            'title',
            'category',
            'description',
            'difficulty',
            'what_you_learn',
            'content',
            'image'
        ]

        widgets = {

            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter course title'
            }),

            'category': forms.Select(attrs={
                'class': 'form-select'
            }),

            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Briefly describe this course...'
            }),

            'difficulty': forms.Select(attrs={
                'class': 'form-select'
            }),

            'what_you_learn': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'What will students learn?'
            }),

            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 10,
                'placeholder': 'Enter the full course content...'
            }),

            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control'
            }),
        }


class CommentForm(forms.ModelForm):

    class Meta:
        model = Comment

        fields = ['content']

        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Write your comment...'
            })
        }


class CommunityPostForm(forms.ModelForm):

    class Meta:
        model = CommunityPost
        fields = ['title', 'category', 'content']
        widgets = {
            'title': forms.TextInput(attrs={
                'placeholder': 'What would you like help with?',
                'maxlength': 180,
            }),
            'category': forms.Select(),
            'content': forms.Textarea(attrs={
                'rows': 8,
                'placeholder': 'Share the details of your question...',
            }),
        }


class CommunityReplyForm(forms.ModelForm):
    content = forms.CharField(
        max_length=10000,
        widget=forms.Textarea(attrs={
            'rows': 5,
            'maxlength': 10000,
            'placeholder': 'Share an answer or ask for more details...',
        }),
    )

    class Meta:
        model = CommunityReply
        fields = ['content']


# =========================================================
# EMAIL SIGNUP FORM
# =========================================================

class EmailSignupForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        min_length=3,
        validators=[
            RegexValidator(
                regex=r'^@?[A-Za-z0-9_]+$',
                message='Use only letters, numbers, and underscores.',
            )
        ],
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Choose your username'
            }
        )
    )

    profile_picture = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                'class': 'profile-upload-input profile-photo-input',
                'accept': 'image/jpeg,image/png,image/webp',
                'data-preview': '#signupProfilePreview',
                'data-placeholder': '#signupProfilePlaceholder',
                'data-error': '#signupProfileError',
            }
        )
    )

    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Enter your email'
            }
        )
    )

    password1 = forms.CharField(
    widget=forms.PasswordInput(
        attrs={
            'class': 'form-control',
            'placeholder': 'Create a password'
        }
    )
)

    password2 = forms.CharField(
            widget=forms.PasswordInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Confirm your password'
                }
            )
        )

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()

        if User.objects.filter(
            email__iexact=email
        ).exists():
            raise forms.ValidationError(
                "An account with this email already exists."
            )

        return email

    def clean_username(self):
        username = self.cleaned_data['username'].strip().removeprefix('@').lower()

        if len(username) < 3:
            raise forms.ValidationError(
                "Username must contain at least 3 letters, numbers, or underscores."
            )

        if User.objects.filter(
            username__iexact=username
        ).exists():
            raise forms.ValidationError(
                f'Username "{username}" already exists. '
                'Please choose another username.'
            )

        return username

    def clean_profile_picture(self):
        return validate_profile_picture(
            self.cleaned_data.get('profile_picture')
        )

    def clean(self):
        cleaned_data = super().clean()

        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2:

            if password1 != password2:
                raise forms.ValidationError(
                    "Passwords do not match."
                )

            try:
                validate_password(password1)
            except ValidationError as error:
                self.add_error(
                    'password1',
                    error
                )

        return cleaned_data

    def save(self):

        email = self.cleaned_data['email']
        username = self.cleaned_data['username']
        password = self.cleaned_data['password1']

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )

        profile_picture = self.cleaned_data.get('profile_picture')
        UserProfile.objects.update_or_create(
            user=user,
            defaults={
                'display_name': username,
                'profile_picture': profile_picture,
            },
        )

        return user


class ProfilePictureForm(forms.Form):
    profile_picture = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'class': 'picture-file-input profile-photo-input',
            'accept': 'image/jpeg,image/png,image/webp',
            'data-preview': '#newProfilePicturePreview',
            'data-placeholder': '#newProfilePicturePlaceholder',
            'data-error': '#profilePictureClientError',
        }),
    )

    def clean_profile_picture(self):
        return validate_profile_picture(
            self.cleaned_data.get('profile_picture')
        )


# =========================================================
# PROJECT FORM
# =========================================================

class ProjectForm(forms.ModelForm):

    class Meta:
        model = Project

        fields = [
            'title',
            'short_description',
            'description',
            'category',
            'tech_stack',
            'status',
            'problem',
            'features',
            'github_url',
            'live_demo_url',
            'looking_for_collaborators',
            'collaborator_types',
        ]

        widgets = {

            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter project title'
            }),

            'short_description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Short description of your project'
            }),

            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 8,
                'placeholder': 'Describe your project in detail...'
            }),

            'category': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Web Development, AI, Mobile'
            }),

            'tech_stack': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Python, Django, React, PostgreSQL'
            }),

            'status': forms.Select(attrs={
                'class': 'form-select'
            }),

            'problem': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'What problem does your project solve?'
            }),

            'features': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'List the main features...'
            }),

            'github_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://github.com/username/project'
            }),

            'live_demo_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://your-project.com'
            }),

            'looking_for_collaborators': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),

            'collaborator_types': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Frontend, Backend, UI/UX'
            }),
        }