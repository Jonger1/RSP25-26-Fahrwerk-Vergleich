"""
Einstieg fuer das Hosting (gunicorn, Vercel, Render, Hugging Face Spaces ...).

    gunicorn wsgi:server

Schaltet den Web-Modus ein (siehe aerostudio/ui/app.py, WEB): geschrieben
wird in eine eigene Ablage, Creo-Knoepfe sind ausgeblendet. Lokal startet man
weiter mit "Aero Studio.bat" bzw. python -m aerostudio.ui.app.
"""

import os

os.environ.setdefault("AEROSTUDIO_WEB", "1")

from aerostudio.ui.app import app as dash_app  # noqa: E402

server = dash_app.server
# Manche Plattformen (Vercel) suchen nach "app", andere nach "application".
app = application = server
