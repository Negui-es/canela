"""Loopback origin for Cloudflare Tunnel. Uses SQLite; Compose uses PostgreSQL."""
import os
import socket
import sys
import secrets
from pathlib import Path

PUBLIC_URL = os.environ.get('CANELA_PUBLIC_URL', 'http://127.0.0.1:8000/')


def open_public_site():
    if os.environ.get('CANELA_OPEN_BROWSER') == '1':
        import webbrowser
        webbrowser.open(PUBLIC_URL)


port=int(os.environ.get('PORT','8000'))
listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
if os.name == 'nt':
    listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
try:
    listener.bind(('127.0.0.1',port))
except OSError:
    listener.close()
    print(f'El puerto {port} ya está ocupado. Si Canela está abierta, usa {PUBLIC_URL}',flush=True)
    open_public_site()
    sys.exit(1)
os.environ.setdefault('DB_ENGINE','sqlite')
os.environ.setdefault('DEBUG','1')
os.environ.setdefault('TRUST_PROXY','0')
if not os.environ.get('SECRET_KEY'):
    secret_file = Path(__file__).resolve().parent / '.local-secret'
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(64), encoding='utf-8')
    os.environ['SECRET_KEY'] = secret_file.read_text(encoding='utf-8').strip()
os.environ.setdefault('DJANGO_SETTINGS_MODULE','canela.settings')
import django
from scripts.build_translations import compile_catalogs
compile_catalogs()
django.setup()
from django.core.management import call_command
call_command('migrate',interactive=False,verbosity=0)
if os.environ['DEBUG'] == '0':
    call_command('collectstatic',interactive=False,verbosity=0)
from canela.wsgi import application
from waitress import serve

print(f'Canela · {PUBLIC_URL}',flush=True)
print('Base local: data/canela.sqlite3 · Fotos: media/',flush=True)
open_public_site()
try:
    serve(application,sockets=[listener],threads=6,max_request_body_size=24*1024*1024,
          trusted_proxy='127.0.0.1' if os.environ.get('TRUST_PROXY')=='1' else None,
          trusted_proxy_headers={'x-forwarded-proto'} if os.environ.get('TRUST_PROXY')=='1' else set())
finally:
    listener.close()
