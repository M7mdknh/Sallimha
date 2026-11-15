from django.db import models


class WorkerHeartbeat(models.Model):
    worker_id = models.CharField(max_length=64, unique=True)
    beat_at = models.DateTimeField()
