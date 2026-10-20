"""
CARMA — Auth endpoint tests
Tests: register, login, refresh, blacklist, change-password, me
"""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from apps.users.models import User


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email='test@carma.ai',
        password='Secure123!',
        first_name='Test',
        last_name='User',
        role='researcher',
    )


@pytest.fixture
def auth_client(api, user):
    res = api.post(reverse('v1:token-obtain'), {
        'email': 'test@carma.ai', 'password': 'Secure123!'
    }, format='json')
    api.credentials(HTTP_AUTHORIZATION=f'Bearer {res.data["access"]}')
    api._refresh = res.data['refresh']
    return api


class TestRegister:
    def test_register_success(self, db, api):
        res = api.post(reverse('v1:user-register'), {
            'email':     'new@carma.ai',
            'first_name':'New', 'last_name':'User',
            'password':  'Secure123!', 'password2': 'Secure123!',
            'role':      'researcher',
        }, format='json')
        assert res.status_code == 201
        assert 'access' in res.data
        assert res.data['user']['role'] == 'researcher'

    def test_register_password_mismatch(self, db, api):
        res = api.post(reverse('v1:user-register'), {
            'email': 'x@carma.ai', 'first_name': 'X', 'last_name': 'Y',
            'password': 'abc', 'password2': 'xyz',
        }, format='json')
        assert res.status_code == 400

    def test_register_admin_blocked(self, db, api):
        res = api.post(reverse('v1:user-register'), {
            'email': 'hacker@carma.ai', 'first_name': 'H', 'last_name': 'A',
            'password': 'Secure123!', 'password2': 'Secure123!', 'role': 'admin',
        }, format='json')
        assert res.status_code == 400


class TestLogin:
    def test_login_success(self, db, user, api):
        res = api.post(reverse('v1:token-obtain'), {
            'email': 'test@carma.ai', 'password': 'Secure123!'
        }, format='json')
        assert res.status_code == 200
        assert 'access' in res.data
        assert 'refresh' in res.data
        assert res.data['user']['role'] == 'researcher'

    def test_login_wrong_password(self, db, user, api):
        res = api.post(reverse('v1:token-obtain'), {
            'email': 'test@carma.ai', 'password': 'WRONG'
        }, format='json')
        assert res.status_code == 401

    def test_token_contains_role(self, db, user, api):
        import jwt
        from django.conf import settings
        res = api.post(reverse('v1:token-obtain'), {
            'email': 'test@carma.ai', 'password': 'Secure123!'
        }, format='json')
        payload = jwt.decode(res.data['access'], settings.SIMPLE_JWT['SIGNING_KEY'],
                             algorithms=['HS256'])
        assert payload['role'] == 'researcher'
        assert payload['email'] == 'test@carma.ai'


class TestRefreshAndBlacklist:
    def test_refresh_token(self, db, auth_client):
        res = auth_client.post(reverse('v1:token-refresh'), {
            'refresh': auth_client._refresh
        }, format='json')
        assert res.status_code == 200
        assert 'access' in res.data

    def test_blacklist_logout(self, db, auth_client):
        res = auth_client.post(reverse('v1:token-blacklist'), {
            'refresh': auth_client._refresh
        }, format='json')
        assert res.status_code == 205


class TestUserMe:
    def test_me_returns_profile(self, db, auth_client):
        res = auth_client.get(reverse('v1:user-me'))
        assert res.status_code == 200
        assert res.data['email'] == 'test@carma.ai'

    def test_me_unauthenticated(self, db, api):
        res = api.get(reverse('v1:user-me'))
        assert res.status_code == 401


class TestChangePassword:
    def test_change_password_success(self, db, auth_client):
        res = auth_client.put(reverse('v1:change-password'), {
            'old_password': 'Secure123!',
            'new_password': 'NewSecure456!',
            'new_password2': 'NewSecure456!',
        }, format='json')
        assert res.status_code == 200

    def test_change_password_wrong_old(self, db, auth_client):
        res = auth_client.put(reverse('v1:change-password'), {
            'old_password': 'WRONG',
            'new_password': 'NewSecure456!',
            'new_password2': 'NewSecure456!',
        }, format='json')
        assert res.status_code == 400


class TestHealthCheck:
    def test_health_ok(self, db, api):
        res = api.get('/health/')
        assert res.status_code == 200
        assert res.data['status'] in ('ok', 'degraded')
