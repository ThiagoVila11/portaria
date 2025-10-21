from pathlib import Path
import environ
import os

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False)
)

# lê .env
environ.Env.read_env(BASE_DIR / '.env')

# Segurança
DEBUG = env("DEBUG", default=False)
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost", "10.0.10.10"])

# Salesforce
SF_USERNAME = env("SF_USERNAME", default=None)
SF_PASSWORD = env("SF_PASSWORD", default=None)
SF_TOKEN    = env("SF_TOKEN", default=None)
SF_DOMAIN   = env("SF_DOMAIN", default="login")

SF = {
    "USERNAME": SF_USERNAME,
    "PASSWORD": SF_PASSWORD,
    "TOKEN": SF_TOKEN,
    "DOMAIN": SF_DOMAIN,
    "SOBJECT": env("SF_SOBJECT", default="reda__Visitor_Log__c"),
}

# Banco de dados
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}

# Internacionalização
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# Arquivos estáticos e de mídia
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Apps
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # apps do projeto
    "accounts.apps.AccountsConfig",
    "portaria.apps.PortariaConfig",
    "condominio",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    #"http://10.1.10.86:8000",
    "http://10.0.10.10:8000",
]

CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

ROOT_URLCONF = "condominio_portaria.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "condominio_portaria.wsgi.application"

# Validação de senha
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Login
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# Celery
CELERY_BROKER_URL = "redis://localhost:6379/0"  # ou amqp://guest:guest@localhost//
CELERY_RESULT_BACKEND = "redis://localhost:6379/0"

CELERY_TIMEZONE = "America/Sao_Paulo"
CELERY_ENABLE_UTC = False

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "atualizar_senhas_encomendas_cada_30min": {
        "task": "portaria.tasks.atualizar_senhas_encomendas",
        "schedule": crontab(minute="*/30"),  # 🔁 a cada 30 minutos
    },
}
