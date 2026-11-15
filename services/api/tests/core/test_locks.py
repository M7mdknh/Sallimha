import pytest

from core.locks import lock_event


@pytest.mark.django_db
def test_lock_event_requires_transaction():
    from django.db import transaction
    with transaction.atomic():
        lock_event(5)  # does not raise inside a transaction


def test_lock_event_outside_transaction_raises(django_db_blocker):
    with django_db_blocker.unblock(), pytest.raises(RuntimeError):
        lock_event(5)
