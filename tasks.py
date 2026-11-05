"""Celery task that runs the AI generation in the background."""

from celery_worker import celery
from services.ai_service import generate_presentation


@celery.task(bind=True, name="tasks.generate_presentation")
def generate_presentation_task(self, payload):
    return generate_presentation(payload)
