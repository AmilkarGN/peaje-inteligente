"""
Configuración principal de Django para el Sistema Inteligente de Control de Peaje (IAM-811).
Autor: Amilkar Hugo Guarachi Nina
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-iam811-peaje-control-amilkar-guarachi-2026",
)

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("ALLOWED_HOSTS", "*").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "api",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
]

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

ROOT_URLCONF = "peaje_config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "frontend_dist",
            BASE_DIR.parent / "frontend" / "dist" / "peaje-angular" / "browser",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "peaje_config.wsgi.application"

# Base de datos (SQLite por defecto en cPanel/Cloud, o MySQL/PostgreSQL mediante variables de entorno)
DB_ENGINE = os.getenv("DB_ENGINE", "django.db.backends.sqlite3")
if DB_ENGINE == "django.db.backends.sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / os.getenv("SQLITE_FILENAME", "peaje_iam811.sqlite3"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": DB_ENGINE,
            "NAME": os.getenv("DB_NAME", "peaje_iam811"),
            "USER": os.getenv("DB_USER", "root"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "3306"),
        }
    }

LANGUAGE_CODE = "es-bo"
TIME_ZONE = "America/La_Paz"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

FRONTEND_BUILD_DIR = BASE_DIR.parent / "frontend" / "dist" / "peaje-angular" / "browser"
STATICFILES_DIRS = [
    d for d in [BASE_DIR / "frontend_dist", FRONTEND_BUILD_DIR] if d.exists()
]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =====================================================================
# VARIABLES DE CONFIGURACIÓN DEL SISTEMA DE PEAJE (SIN RECURSOS LOCALES)
# =====================================================================
# URL del Endpoint de Inferencia en RunPod o Google Colab
INFERENCE_URL = os.getenv("INFERENCE_URL", "https://glad-blocked-cod-colon.trycloudflare.com").rstrip("/")

# Google OAuth 2.0 Client ID (Web y Android)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_ANDROID_CLIENT_ID = os.getenv("GOOGLE_ANDROID_CLIENT_ID", "")

# Pusher Channels para Tiempo Real en Hosting Compartido / Cloud
PUSHER_APP_ID = os.getenv("PUSHER_APP_ID", "")
PUSHER_KEY = os.getenv("PUSHER_KEY", "")
PUSHER_SECRET = os.getenv("PUSHER_SECRET", "")
PUSHER_CLUSTER = os.getenv("PUSHER_CLUSTER", "us2")

# API Key para el Agente Conversacional (Google Gemini Function Calling)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Clave para el dispositivo de hardware Arduino en la nube (Bono +5 pts)
HARDWARE_API_KEY = os.getenv("HARDWARE_API_KEY", "IAM811-ARDUINO-CLOUD-KEY")
