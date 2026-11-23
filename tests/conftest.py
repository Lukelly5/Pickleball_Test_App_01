import pytest


@pytest.fixture(autouse=True)
def _fast_password_hasher(settings):
    """Tests create many users; the real hasher is deliberately slow."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
