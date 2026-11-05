"""Celery app configured with Redis broker and backend."""

import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

broker = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL") or "redis://localhost:6379/0"
backend = os.getenv("CELERY_RESULT_BACKEND") or broker

celery = Celery(
    "slidewala",
    broker=broker,
    backend=backend,
)

celery.conf.update(
    task_track_started=True,
    task_time_limit=300,        # hard kill after 5 min
    task_soft_time_limit=240,   # raise SoftTimeLimitExceeded at 4 min
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)
