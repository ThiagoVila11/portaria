from pathlib import Path
from pathlib import Path
import environ
import os


BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
DEBUG=(bool, False)
)


# lê .env
environ.Env.read_env(BASE_DIR / '.env')


DEBUG = env('DEBUG')
SECRET_KEY = env('SECRET_KEY')
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "10.1.10.86"] #env.list('ALLOWED_HOSTS', default=['127.0.0.1', 'localhost'])


SF_USERNAME = os.getenv("SF_USERNAME")       # integracao@...
SF_PASSWORD = os.getenv("SF_PASSWORD")
SF_TOKEN    = os.getenv("SF_TOKEN")
SF_DOMAIN   = os.getenv("SF_DOMAIN", "login")   # "test" p/ sandbox
#OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")    # se for usar OCR

# Banco de dados via DATABASE_URL
DATABASES = {
'default': env.db('DATABASE_URL')
}


LANGUAGE_CODE = env('LANGUAGE_CODE', default='pt-br')
TIME_ZONE = env('TIME_ZONE', default='America/Sao_Paulo')
USE_I18N = True
USE_TZ = True


STATIC_URL = 'static/'
MEDIA_URL = '/media/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = BASE_DIR / 'media'


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
#SECRET_KEY = 'django-insecure-^wq#(p+95ttzj=p5x_leersh#k#cag$zb+u_drhx8%$n!r=_bt'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # apps do projeto
    #'accounts',  # <-- descomente se não usar apps.py
    "accounts.apps.AccountsConfig",
    "portaria.apps.PortariaConfig",
    'condominio',
    
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",   # ← aqui
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:8000", "http://localhost:8000", "http://10.1.10.86:8000"]
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
ROOT_URLCONF = 'condominio_portaria.urls'

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [ BASE_DIR / "templates" ],   # <-- importante
        "APP_DIRS": True,                    # <-- mantém busca em templates dos apps
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",   # LoginView costuma precisar
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = 'condominio_portaria.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

SF = {
    "USERNAME": env("SF_USERNAME", default=None),
    "PASSWORD": env("SF_PASSWORD", default=None),
    "TOKEN":    env("SF_TOKEN",    default=None),
    "DOMAIN":   env("SF_DOMAIN",   default="login"),
    "SOBJECT":  env("SF_SOBJECT",  default="reda__Visitor_Log__c"),
}




# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
