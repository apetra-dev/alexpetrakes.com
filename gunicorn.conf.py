import os
import logging

logger = logging.getLogger(__name__)

port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"
workers = int(os.environ.get("WEB_CONCURRENCY", 1))
accesslog = "-"
errorlog = "-"
loglevel = "info"

logger.info(f"Gunicorn configured: bind={bind}, workers={workers}")
