"""Real API/DB checks for bounded everyday actions from a wall account."""
from datetime import date, timedelta
from uuid import uuid4
from unittest.mock import patch

import pytest
from test_pets import client, login, create
from app import routines, config
from app.auth.service import auth_service
from app.db import connect, init_db
from app.family_visibility import save_action_rules, save_visibility_rules
from app.family_tasks import family_tasks_service, HomeAssistantTasksClient, FamilyTasksSettings, TaskSource
from app.family_task_assignments import FamilyTaskAssignmentStore
from app.home_assistant import HomeAssistantConnection


def test_wall_pet_care_repeat_retry_undo_and_boundary(client):
    owner = login(client, 'owner'); pet = create(client, owner)
    wall = login(client, 'wall_display')
    day = client.get('/api/family/pets').json()['today']
    for task in ['food', 'water', 'walk']:
        url = f'/api/family/pets/{pet}/care/{task}/entries'
        payload = {'day': day, 'request_id': str(uuid4())}
        assert client.post(url, json=payload).status_code == 403
        first = client.post(url, headers=wall, json=payload)
        assert first.status_code == 201
        assert client.post(url, headers=wall, json=payload).json() == first.json()
        assert client.post(url, headers=wall, json={**payload, 'request_id': str(uuid4())}).status_code == 201
        assert client.delete(f"/api/family/pets/{pet}/care/entries/{first.json()['id']}", headers=wall).status_code == 200
        assert client.post(url, headers=wall, json={**payload, 'day':'1990-01-01'}).status_code == 409
    assert client.get('/api/family/pets').json()['pets'][0]['care_counts'] == {'food':1, 'water':1, 'walk':1}
    assert client.post(f'/api/family/pets/{pet}/expenses', headers=wall, json={}).status_code == 403
    assert client.put(f'/api/family/pets/{pet}/reminders/1', headers=wall, json={'completed':True}).status_code == 403
    init_db()
    assert client.get('/api/family/pets').json()['pets'][0]['care_counts']['food'] == 1


def test_wall_shopping_and_meal_shared_persistence_and_csrf(client):
    wall = login(client, 'wall_display')
    base = '/api/family/shopping'
    assert client.post(base, json={'name':'Ugen'}).status_code == 403
    lid = client.post(base, headers=wall, json={'name':'Ugen'}).json()['id']
    item = client.post(f'{base}/{lid}/items', headers=wall, json={'name':'Mælk'}).json()['id']
    assert client.put(f'{base}/{lid}/items/{item}/state', json={'done':True}).status_code == 403
    assert client.put(f'{base}/{lid}/items/{item}/state', headers=wall, json={'done':True}).status_code == 200
    day = client.get('/api/family/planning').json()['today']
    body = {'meal':'Pasta', 'cook':'Dennis', 'ingredients':['Pasta','Tomater'], 'reminders':['Madpakke']}
    assert client.put(f'/api/family/planning/{day}', json=body).status_code == 403
    assert client.put(f'/api/family/planning/{day}', headers=wall, json=body).status_code == 200
    result = client.post(f'/api/family/planning/{day}/shopping', headers=wall, json={'list_id':lid})
    assert result.json()['added'] == 2
    assert client.post(f'/api/family/planning/{day}/shopping', headers=wall, json={'list_id':lid}).json()['added'] == 0
    for method, url, payload in [('put', f'{base}/{lid}', {'name':'Changed'}), ('delete', f'{base}/{lid}', None), ('delete', f'{base}/{lid}/completed', None), ('delete', f'{base}/{lid}/items/{item}', None), ('put', f'{base}/{lid}/items/{item}', {'name':'Changed'})]:
        assert client.request(method, url, headers=wall, **({'json':payload} if payload else {})).status_code == 403
    init_db()
    login(client, 'adult')  # A different login reads the same persisted household data.
    assert client.get('/api/family/planning').json()['days'][0]['meal'] == 'Pasta'
    saved = client.get(base).json()['lists'][0]['items']
    assert len(saved) == 3 and next(i for i in saved if i['id'] == item)['done'] == 1


def test_wall_medication_checkoff_not_plan_editor(client):
    owner = login(client,'owner'); uid = client.get('/api/auth/me').json()['user_id']
    base = '/api/family/medication'; day = date(2026,10,9)
    body = {'user_id':uid, 'name':'Testmedicin', 'instructions':'Not for shared display', 'start_date':day.isoformat(), 'times':['08:00','20:00']}
    with patch('app.medication.today', return_value=day):
        pid = client.post(base, headers=owner, json=body).json()['id']
        original = client.get(base).json()['plans'][0]
        wall = login(client,'wall_display')
        entry = client.get(base+'/display').json()['entries'][0]
        url = f'{base}/display/{pid}/record'
        payload = {'revision':entry['revision'], 'day':day.isoformat(), 'slot':entry['time'], 'status':'taken'}
        for bad_headers in [None, {'X-CSRF-Token':'bad'}]:
            assert client.put(url, headers=bad_headers, json=payload).status_code == 403
        for _ in range(2): assert client.put(url, headers=wall, json=payload).status_code == 200
        assert client.get(base+'/display').json()['entries'][0]['status'] == 'taken'
        with connect() as conn:
            row = conn.execute('SELECT * FROM medication_records').fetchall()
            assert len(row) == 1 and row[0]['recorded_by'] == client.get('/api/auth/me').json()['user_id']
        assert client.put(url, headers=wall, json={**payload, 'status':'skipped'}).status_code == 422
        assert client.put(url, headers=wall, json={**payload, 'status':'unmarked'}).status_code == 200
        assert client.get(base+'/display').json()['entries'][0]['status'] == 'unmarked'
        for changed in [{'day':(day-timedelta(days=1)).isoformat()}, {'slot':'09:00'}, {'revision':'stale'}]:
            assert client.put(url, headers=wall, json={**payload, **changed}).status_code == 409
        assert client.post(base, headers=wall, json=body).status_code == 403
        assert client.put(f'{base}/{pid}', headers=wall, json={**body,'revision':original['revision']}).status_code == 403
        assert client.delete(f'{base}/{pid}', headers=wall).status_code == 403
        assert client.get(base).status_code == 403
        assert client.put(f'{base}/{pid}/record', headers=wall, json=payload).status_code == 403
        # Adult changes to a plan invalidate the shared display's old version.
        client.post('/api/auth/login',json={'username':'owner','password':'Pets-Test-Password-123!'})
        owner = {'X-CSRF-Token':client.get('/api/auth/me').json()['csrf_token']}
        assert client.put(f'{base}/{pid}', headers=owner, json={**body,'revision':original['revision'],'times':['09:00']}).status_code == 200
        client.post('/api/auth/login',json={'username':'wall_display','password':'Pets-Test-Password-123!'})
        wall = {'X-CSRF-Token':client.get('/api/auth/me').json()['csrf_token']}
        assert client.put(url, headers=wall, json=payload).status_code == 409
        child = login(client,'child')
        assert client.put(url, headers=child, json=payload).status_code == 403
        client.cookies.clear()
        assert client.put(url, json=payload).status_code == 401


def test_wall_tasks_assignment_completion_owner_denial_and_visibility(client, monkeypatch):
    owner = login(client,'owner')
    uid = auth_service.create_user('kid','Barn','child','Board-Test-Password-123!')['user_id']
    monkeypatch.setattr(family_tasks_service,'settings_loader',lambda: FamilyTasksSettings(HomeAssistantConnection('http://synthetic','test-only',1),(TaskSource('todo.family','family','Familie'),),0,30,50))
    monkeypatch.setattr(family_tasks_service,'assignment_store',FamilyTaskAssignmentStore(config.DB_PATH))
    items = []
    monkeypatch.setattr(HomeAssistantTasksClient,'fetch',lambda self:([{'key':'family','label':'Familie','items':[dict(i) for i in items]}],0))
    monkeypatch.setattr(HomeAssistantTasksClient,'add',lambda self,source,summary,description: items.append({'uid':'new','summary':summary,'description':description,'due':None}))
    monkeypatch.setattr(HomeAssistantTasksClient,'complete',lambda self,source,item_uid: items.clear())
    family_tasks_service.clear_cache()
    wall = login(client,'wall_display'); base='/api/family/tasks/family/items'
    payload={'summary':'Skrald','assignee_id':uid}
    assert client.post(base,json=payload).status_code == 403
    assert client.post(base,headers=wall,json=payload).status_code == 200
    snapshot=client.get('/api/family/tasks').json()
    assert snapshot['can_add'] and snapshot['can_complete'] and not snapshot['can_edit'] and not snapshot['can_remove']
    assert snapshot['lists'][0]['items'][0]['assignee_id'] == uid
    assert client.put(base,headers=wall,json={'item':'new','summary':'Change'}).status_code == 403
    assert client.request('DELETE',base,headers=wall,json={'item':'new'}).status_code == 403
    assert client.post('/api/family/tasks/family/complete',headers=wall,json={'item':'new'}).status_code == 200
    save_action_rules({'wall_display':{'task_add':False,'task_complete':False}},db_path=config.DB_PATH)
    assert client.post(base,headers=wall,json=payload).status_code == 403
    assert client.post('/api/family/tasks/family/complete',headers=wall,json={'item':'new'}).status_code == 403
    save_action_rules({'wall_display':{'task_add':True,'task_complete':True}},db_path=config.DB_PATH)
    save_visibility_rules({'wall_display':{'tasks':False}},db_path=config.DB_PATH)
    assert client.post(base,headers=wall,json=payload).status_code == 403
    assert client.get('/api/family/tasks').json()['lists'] == []


def test_wall_existing_routines_progress_and_protected_definitions(client, monkeypatch, tmp_path):
    login(client,'adult')
    monkeypatch.setattr(routines,'routine_store',routines.RoutineStore(tmp_path/'routines.json'))
    wall = login(client,'wall_display')
    snapshot=client.get('/api/family/routines').json()
    uid=snapshot['selected_person_id']
    body={'person_id':uid,'expected_index':0}
    url='/api/family/routines/morning/complete'
    assert client.post(url,json=body).status_code == 403
    assert client.post(url,headers=wall,json=body).status_code == 200
    assert client.get('/api/family/routines').json()['routines']['morning']['current_index'] == 1
    assert client.get('/api/family/routines/definitions').status_code == 403
    assert client.put('/api/family/routines/definitions/morning',headers=wall,json={}).status_code == 403


@pytest.mark.parametrize('path',['/admin','/api/admin/users','/api/admin/home-modules/config','/api/admin/family-actions','/api/admin/family-visibility','/api/actions','/api/settings'])
def test_wall_admin_remains_forbidden(client,path):
    login(client,'wall_display')
    assert client.get(path).status_code == 403
