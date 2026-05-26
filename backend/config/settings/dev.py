"""Development settings."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = ["*"]

CORS_ALLOWED_ORIGINS = env(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173"],
)

# Password reset and similar emails print to the runserver console in dev.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
