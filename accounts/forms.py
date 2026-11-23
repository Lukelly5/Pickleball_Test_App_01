from django import forms
from django.contrib.auth.forms import AuthenticationForm


class EmailLoginForm(AuthenticationForm):
    """Django's login form, labelled for email addresses."""

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        field = self.fields["username"]
        field.label = "Email"
        field.widget = forms.EmailInput(
            attrs={"autocomplete": "email", "autofocus": True, "autocapitalize": "none"}
        )
