"""sns_app package initializer
Exposes the Flask app for `python -m sns_app` style runs if desired.
"""
from .app import app

__all__ = ["app"]
