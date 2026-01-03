"""Convenience runner inside the package."""
import os
from .app import app

if __name__ == '__main__':
    host = os.environ.get('SNS_HOST', '0.0.0.0')
    try:
        port = int(os.environ.get('SNS_PORT', '5000'))
    except ValueError:
        port = 5000
    debug = os.environ.get('SNS_DEBUG', '0') != '0'
    app.run(host=host, port=port, debug=debug)
