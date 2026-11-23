from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class Organization(models.Model):
    name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def get_by_natural_key(self, email):
        """Log in by email whatever its letter case; an exact match wins if two differ only by case."""
        matches = list(self.filter(email__iexact=email)[:2])
        if len(matches) == 1:
            return matches[0]
        return self.get(email=email)

    def create_superuser(self, email, password, **extra):
        extra["is_staff"] = True
        extra["is_superuser"] = True
        extra["is_admin"] = True
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )
    # League Admin role (PRD section 2); separate from is_staff (Django admin access).
    is_admin = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email
