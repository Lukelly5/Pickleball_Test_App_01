from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import SetPasswordForm
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy

from league.models import Invite

from .forms import EmailLoginForm
from .invites import InviteError, accept_invite, check_invite
from .models import User
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


def invite_accept(request, token):
    """P1 accept invite: choose a password, then land on your home page."""
    invite = get_object_or_404(Invite.objects.select_related("organization"), token=token)
    context = {"invite": invite, "error": None, "form": None}
    try:
        check_invite(invite)
    except InviteError as error:
        context["error"] = str(error)
        return render(request, "accounts/invite_accept.html", context)

    form = SetPasswordForm(User(email=invite.email), request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = accept_invite(token, form.cleaned_data["new_password1"])
        except InviteError as error:
            context["error"] = str(error)
            return render(request, "accounts/invite_accept.html", context)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Welcome to Stryde.")
        return redirect("home")
    context["form"] = form
    return render(request, "accounts/invite_accept.html", context)
