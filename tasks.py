
"""SlideWala - background presentation generation tasks."""

import logging

from celery_worker import celery


logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    name="tasks.generate_presentation_task",
    max_retries=0,
)
def generate_presentation_task(self, payload):
    """Generate a presentation in the background."""

    from services.ai_service import (
        AIConfigError,
        AIResponseError,
        generate_presentation,
    )

    try:
        logger.info(
            "Starting SlideWala job %s",
            self.request.id,
        )

        deck = generate_presentation(payload)

        logger.info(
            "SlideWala job %s completed successfully",
            self.request.id,
        )

        return deck

    except (AIConfigError, AIResponseError, ValueError):
        logger.exception(
            "SlideWala job %s failed",
            self.request.id,
        )
        raise

    except Exception:
        logger.exception(
            "Unexpected error in SlideWala job %s",
            self.request.id,
        )
        raise
