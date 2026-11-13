import json
import time

import httpx
import pytest

from swarm.config import Settings
from swarm.guest_invite import create_invite_app


@pytest.fixture
def invite_host(tmp_path):
    settings = Settings(token="control-token-" * 4, state_dir=str(tmp_path))
    access = {"token": "guest-only-pass-" * 3, "expires_at": time.time() + 120, "port": 8002}
    url = "https://demo.example/#pass=" + access["token"]
    (tmp_path / "guest-pass.json").write_text(json.dumps(access))
    (tmp_path / "guest-url.txt").write_text(url)
    return settings, access, url


def clients(settings, access, *, status_code=200, remaining=7, ready=True, busy=False, source="127.0.0.1"):
    calls = []
    async def status(request):
        calls.append(request)
        assert str(request.url) == "http://127.0.0.1:8002/api/status"
        assert request.headers["authorization"] == "Bearer " + access["token"]
        return httpx.Response(status_code, json={"remaining_jobs": remaining, "ready": ready, "busy": busy,
            "expires_at": access["expires_at"], "private": "MUST NOT RETURN"})
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(status))
    app = create_invite_app(settings, upstream)
    local = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(source, 12345)),
        base_url="http://127.0.0.1:8003", headers={"Authorization": "Bearer " + settings.token,
                                                "Origin": "http://localhost:8000"})
    return local, upstream, calls


async def test_invite_returns_current_qr_without_exposing_controls(invite_host):
    settings, access, url = invite_host
    local, upstream, calls = clients(settings, access)
    async with local, upstream:
        result = await local.get('/api/guest-invite')
        assert result.status_code == 200
        data = result.json()
        assert data["status"] == "available" and data["url"] == url
        assert data["qr"].startswith('data:image/png;base64,iVBOR')
        assert data["expires_at"] == access["expires_at"] and data["remaining_jobs"] == 7
        assert settings.token not in result.text and "MUST NOT RETURN" not in result.text
        assert result.headers['cache-control'] == 'no-store'
        assert result.headers['access-control-allow-origin'] == 'http://localhost:8000'
        for method, path in [('GET','/api/bootstrap'), ('GET','/api/state'), ('GET','/openapi.json'),
                             ('POST','/api/session/start'), ('GET','/guest-pass.json')]:
            assert (await local.request(method, path)).status_code == 404
        assert len(calls) == 1


@pytest.mark.parametrize('headers,code', [
    ({'Authorization':''},401), ({'Authorization':'Bearer guest-only-pass-' * 3},401),
    ({'Origin':'https://attacker.example'},403), ({'Host':'attacker.example:8003'},403)])
async def test_invite_rejects_unauthorized_or_cross_origin_access(invite_host, headers, code):
    settings, access, _ = invite_host
    local, upstream, calls = clients(settings, access)
    async with local, upstream:
        result = await local.get('/api/guest-invite', headers=headers)
        assert result.status_code == code and not calls
        assert access['token'] not in result.text


async def test_invite_rejects_lan_and_permits_only_local_cors_preflight(invite_host):
    settings, access, _ = invite_host
    local, upstream, calls = clients(settings, access, source='192.168.1.20')
    async with local, upstream:
        assert (await local.get('/api/guest-invite')).status_code == 403
        assert not calls
        for origin, code in [('http://localhost:8000',200), ('https://attacker.example',400)]:
            result = await local.options('/api/guest-invite', headers={'Origin':origin,
                'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'authorization'})
            assert result.status_code == code


@pytest.mark.parametrize('kind', ['missing','expired','mismatch','control-port','malformed'])
async def test_unusable_invite_never_releases_link_or_qr(invite_host, kind):
    settings, access, _ = invite_host
    path = settings.state_path / 'guest-pass.json'
    if kind == 'missing':
        path.unlink()
    elif kind == 'malformed':
        path.write_text('[]')
    else:
        if kind == 'expired': access['expires_at'] = time.time() - 1
        if kind == 'mismatch': access['token'] = 'different-guest-pass-' * 3
        if kind == 'control-port': access['port'] = settings.api_port
        path.write_text(json.dumps(access))
    local, upstream, calls = clients(settings, access)
    async with local, upstream:
        response = await local.get('/api/guest-invite')
        data = response.json()
        assert data['status'] in ('missing','expired','invalid')
        assert 'url' not in data and 'qr' not in data and not calls


@pytest.mark.parametrize('code,remaining,expected', [(401,7,'expired'),(410,7,'expired'),(503,7,'offline'),(200,0,'exhausted')])
async def test_gateway_invalidates_unusable_invites(invite_host, code, remaining, expected):
    settings, access, _ = invite_host
    local, upstream, _ = clients(settings, access, status_code=code, remaining=remaining)
    async with local, upstream:
        data = (await local.get('/api/guest-invite')).json()
        assert data['status'] == expected and 'url' not in data and 'qr' not in data


async def test_loading_swarm_can_be_invited_without_claiming_ready(invite_host):
    settings, access, _ = invite_host
    local, upstream, _ = clients(settings, access, ready=False)
    async with local, upstream:
        data = (await local.get('/api/guest-invite')).json()
        assert data['status'] == 'available' and data['ready'] is False
