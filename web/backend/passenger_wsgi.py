"""
Archivo de entrada WSGI para Hosting Compartido (cPanel - Setup Python App / Phusion Passenger).
También permite servir la aplicación Django + compilado de Angular en un solo subdominio HTTPS.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "peaje_config.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
