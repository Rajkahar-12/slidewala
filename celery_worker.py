
"""SlideWala - Celery background worker configuration."""

import os
from pathlib import Path

from celery import Celery
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0"
)


celery = Celery(
    "slidewala",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],
)


celery.conf.update(
    # Task serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Time settings
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,

    # Results
    task_ignore_result=False,
    result_expires=3600,

    # Connection reliability
    broker_connection_retry_on_startup=True,
)
