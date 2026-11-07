"""Container entrypoint: migrate, then serve through Waitress."""
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','canela.settings')
import django
django.setup()
from django.core.management import call_command
call_command('migrate',interactive=False)
from canela.wsgi import application
from waitress import serve
serve(application,host='0.0.0.0',port=8000,threads=8,
      max_request_body_size=24*1024*1024, trusted_proxy='*' if os.environ.get('TRUST_PROXY')=='1' else None,
      trusted_proxy_headers={'x-forwarded-proto'} if os.environ.get('TRUST_PROXY')=='1' else set())
