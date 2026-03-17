import os

bind    = f"0.0.0.0:{os.environ.get('PORT', 5001)}"
workers = 2
timeout = 120

# Load the Flask app in the master process before forking workers.
# This ensures boto3 (and any ObjC-linked libs) are fully initialised
# in the master so workers inherit a clean, stable state after fork.
preload_app = True
