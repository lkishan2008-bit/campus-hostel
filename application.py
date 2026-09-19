"""
AWS Elastic Beanstalk WSGI Entry Point for Campus Hostel Companion.

Elastic Beanstalk expects a default file named `application.py`
and a WSGI callable named `application`.
"""

from app import app as application

if __name__ == "__main__":
    application.run()
