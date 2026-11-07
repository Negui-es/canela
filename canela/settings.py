import os
import secrets
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get('DEBUG', '1') == '1'
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('SECRET_KEY es obligatoria en producción.')
    secret_file = BASE_DIR / '.local-secret'
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(64), encoding='utf-8')
    SECRET_KEY = secret_file.read_text(encoding='utf-8').strip()
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
CSRF_TRUSTED_ORIGINS = [x for x in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if x]
ALLOW_NEW_ACCOUNTS = os.environ.get('ALLOW_NEW_ACCOUNTS', '0') == '1'
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'studio',
]
MIDDLEWARE = [
    'canela.errors.PublicErrorMiddleware',
    'canela.security.OriginSecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware',
    'studio.middleware.PrivateCacheMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware', 'canela.i18n.BrowserLocaleMiddleware',
    'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'canela.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': False,
    'OPTIONS': {'loaders': [
        'django.template.loaders.filesystem.Loader', 'django.template.loaders.app_directories.Loader',
    ] if DEBUG else [('django.template.loaders.cached.Loader', [
        'django.template.loaders.filesystem.Loader', 'django.template.loaders.app_directories.Loader',
    ])], 'context_processors': [
        'django.template.context_processors.request', 'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages', 'studio.context.navigation',
    ]},
}]
WSGI_APPLICATION = 'canela.wsgi.application'
DB_ENGINE = os.environ.get('DB_ENGINE', 'postgresql')
if DB_ENGINE == 'sqlite':
    (BASE_DIR / 'data').mkdir(exist_ok=True)
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'data' / 'canela.sqlite3'}}
else:
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql', 'NAME': os.environ.get('POSTGRES_DB', 'canela'),
        'USER': os.environ.get('POSTGRES_USER', 'canela'), 'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
        'HOST': os.environ.get('POSTGRES_HOST', 'db'), 'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': 60,
    }}
AUTH_USER_MODEL = 'studio.User'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = 'en'
LANGUAGES = [('es','Español'),('en','English'),('fr','Français'),('de','Deutsch'),('it','Italiano')]
LOCALE_PATHS = [BASE_DIR / 'locale']
TIME_ZONE = 'Atlantic/Canary'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
WHITENOISE_USE_FINDERS = DEBUG
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage' if DEBUG else 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
MEDIA_ROOT = BASE_DIR / 'media'
# No public MEDIA_URL route: every photograph is served through access checks.
MEDIA_URL = '/protected-media/'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
DATA_UPLOAD_MAX_MEMORY_SIZE = 24 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_FAILURE_VIEW = 'canela.errors.csrf_failure'
SECURE_SSL_REDIRECT = not DEBUG
SECURE_REDIRECT_EXEMPT = [r'^health/$']
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
X_FRAME_OPTIONS = 'DENY'
if os.environ.get('TRUST_PROXY', '0') == '1':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
