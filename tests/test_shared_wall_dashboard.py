from datetime import date, timedelta
from unittest.mock import patch

from test_pets import client, login, create


def test_wall_shared_modules_are_read_only_and_role_is_visible(client):
    owner = login(client, 'owner')
    pet = create(client, owner)
    day = client.get('/api/family/planning').json()['today']
    client.put(f'/api/family/planning/{day}', headers=owner, json={'meal':'Pasta','reminders':['Madpakke']})
    list_id = client.post('/api/family/shopping',headers=owner,json={'name':'Familien'}).json()['id']
    headers = login(client, 'wall_display')
    html = client.get('/').text
    for module in ['pets','planning','shopping','energy','cameras','medication']:
        assert f'data-family-card="{module}"' in html
    assert 'data-medication-display="true"' in html
    assert 'Vægskærm</p>' in html
    assert 'href="/admin"' not in html
    assert 'data-family-card="technical"' not in html
    assert client.get('/admin').status_code == 403
    assert client.get('/api/family/planning').json()['can_edit'] is False
    pets = client.get('/api/family/pets').json()
    assert pets['can_care'] is False and pets['can_edit'] is False
    shop = client.get('/api/family/shopping').json()
    assert not shop['can_shop'] and not shop['can_manage']
    assert client.put(f'/api/family/planning/{day}',headers=headers,json={'meal':'Changed'}).status_code == 403
    assert client.post(f'/api/family/shopping/{list_id}/items',headers=headers,json={'name':'Changed'}).status_code == 403
    assert client.get(f'/api/family/pets/{pet}/expenses').status_code == 403
    assert client.post('/api/family/pets',headers=headers,json={'name':'Changed'}).status_code == 403
    assert client.get('/api/family/energy').status_code == 200
    assert client.get('/api/family/cameras').status_code == 200
    assert client.get('/api/admin/home-modules').status_code == 403
    assert client.put('/api/admin/home-modules',headers=headers,json={}).status_code == 403
    # Existing dedicated screen layouts remain separate.
    dedicated = client.get('/wall')
    assert dedicated.status_code == 200
    assert 'data-wall-dashboard="true"' in dedicated.text
    assert 'data-family-card="planning"' not in dedicated.text
    assert 'data-family-card="medication"' not in dedicated.text


def test_medication_display_today_only_and_no_private_plan_fields(client):
    headers = login(client,'owner')
    person = client.get('/api/auth/me').json()['user_id']
    day = date(2026,10,8)
    payload={'user_id':person,'name':'Testplan','instructions':'Private dosing instruction','start_date':'2026-10-07','times':['08:00'],'weekdays':list(range(7))}
    with patch('app.medication.today',return_value=day):
        plan = client.post('/api/family/medication',headers=headers,json=payload).json()['id']
        original = client.get('/api/family/medication').json()['plans'][0]
        client.put(f'/api/family/medication/{plan}/record',headers=headers,json={'revision':original['revision'],'day':day.isoformat(),'slot':'08:00','status':'taken'})
        client.post('/api/family/medication',headers=headers,json={**payload,'name':'Future secret','start_date':(day+timedelta(days=1)).isoformat()})
        wall = login(client,'wall_display')
        result = client.get('/api/family/medication/display')
        assert result.status_code == 200 and result.headers['cache-control']=='no-store'
        assert result.json()['entries'][0]['status']=='taken'
        assert result.json()['entries'][0]['read_only'] is True
        assert len(result.json()['entries']) == 1
        for forbidden in ['Private dosing instruction','Future secret','instructions','recorded_by','plan_snapshot','revision','password_hash']:
            assert forbidden not in result.text
        assert client.get('/api/family/medication').status_code == 403
        assert client.put(f'/api/family/medication/{plan}/record',headers=wall,json={'revision':original['revision'],'day':day.isoformat(),'slot':'08:00','status':'unmarked'}).status_code == 403
        login(client,'child')
        assert client.get('/api/family/medication/display').status_code == 403
        client.cookies.clear()
        assert client.get('/api/family/medication/display').status_code == 401
