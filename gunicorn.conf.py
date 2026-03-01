import os

bind = f"0.0.0.0:{os.environ.get('PORT', 5001)}"
workers = 2
timeout = 120
