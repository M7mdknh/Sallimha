import itertools

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

_n = itertools.count(1)


def login_as(staff, client=None):
    user = get_user_model().objects.create_user(username=f"user{next(_n)}", password="correct horse battery 9")
    staff.user = user
    staff.save(update_fields=["user"])
    client = client or APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def as_supervisor(world):
    return login_as(world.supervisor)


@pytest.fixture
def as_manager(world):
    return login_as(world.manager)
