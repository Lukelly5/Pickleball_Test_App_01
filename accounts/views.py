from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from django.urls import reverse_lazy

from .forms import EmailLoginForm
from .roles import role_of


def home(request):
    """Send each person to their home page: admins to My Events, players to My Games."""
    if not request.user.is_authenticated:
        return redirect("login")
    if role_of(request.user) == "player":
        return redirect("my_games")
    return redirect("event_list")


class LoginView(auth_views.LoginView):
    form_class = EmailLoginForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    next_page = "login"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.info(request, "You're logged out.")
        return response


class AccountView(auth_views.PasswordChangeView):
    template_name = "accounts/account.html"
    success_url = reverse_lazy("account")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Your password was changed.")
        return response


class PasswordResetView(auth_views.PasswordResetView):
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
