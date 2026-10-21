"""
Shared pytest fixtures for the CARMA backend test-suite.
"""
import pytest
from rest_framework.test import APIClient

from apps.users.models import User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        email='admin@carma.test', password='Carma-Test-2026!',
        first_name='Ada', last_name='Admin', username='admin')


@pytest.fixture
def researcher_user(db):
    return User.objects.create_user(
        email='researcher@carma.test', password='Carma-Test-2026!',
        first_name='Rita', last_name='Researcher', username='researcher',
        role='researcher')


@pytest.fixture
def reviewer_user(db):
    return User.objects.create_user(
        email='reviewer@carma.test', password='Carma-Test-2026!',
        first_name='Rev', last_name='Viewer', username='reviewer',
        role='reviewer')


@pytest.fixture
def auth_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client
