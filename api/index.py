"""
Vercel Serverless Function Entry Point for Campus Hostel Companion.

This module exposes the Flask WSGI application instance as `app`
without starting a local development server.
"""

import sys
import os

# Add the project root directory to sys.path so 'app' and other modules can be imported
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app
