from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "b2b_saas_worker",
    broker=settings.CELERY_BROKER_URL
)

# Do NOT configure a result backend, as PostgreSQL is our source of truth.

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)

# Explicitly discover tasks
celery_app.autodiscover_tasks(["app.tasks"])
