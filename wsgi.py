"""
Production entrypoint. Render (and most hosts) run a real WSGI server
(gunicorn) instead of Flask's built-in development server — gunicorn
looks for a module-level variable literally named `app`, which is what
this file provides.
"""
import jobbot

app = jobbot.build_flask_app()
