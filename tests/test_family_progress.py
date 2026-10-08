from datetime import date
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_pets import client, login
from app.auth.service import auth_service
from app.db import connect
from app.family_progress import award_completion


def seed(client):
    owner=login(client,'owner')
    auth_service.update_profile(client.get('/api/auth/me').json()['user_id'],'blue',True)
    child=auth_service.create_user('kid','Barn','child','Progress-Test-Password-123!')['user_id']
    config={'goal':'Fredagens film','target':3,'rules':[{'kind':'chore','source':'trash','label':'Skrald','stars':1},{'kind':'routine','source':'morning','label':'Morgenrutine','stars':2}]}
    assert client.put(f'/api/family/rewards/{child}',headers=owner,json=config).status_code==200
    return owner,child,config


def board(client,uid):
    return next(p for p in client.get('/api/family/rewards').json()['people'] if p['user_id']==uid)


def test_rewards_idempotent_balance_and_adult_redemption(client):
    headers,uid,config=seed(client)
    day=client.get('/api/family/rewards').json()['today']
    for _ in range(2):
        assert client.post(f'/api/family/rewards/{uid}/complete',headers=headers,json={'source':'trash','day':day}).status_code==200
    for _ in range(2):award_completion('routine','morning','test',uid,day)
    p=board(client,uid)
    assert (p['balance'],p['earned'],p['spent'])==(3,3,0)
    assert len(p['events'])==2
    payload={'goal':config['goal'],'target':3}
    assert client.post(f'/api/family/rewards/{uid}/redeem',headers=headers,json=payload).status_code==200
    assert client.post(f'/api/family/rewards/{uid}/redeem',headers=headers,json=payload).status_code==409
    p=board(client,uid);assert (p['earned'],p['spent'],p['balance'])==(3,3,0)
    assert client.put(f'/api/family/rewards/{uid}',headers=headers,json={**config,'rules':[]}).status_code==200
    assert board(client,uid)['earned']==3


def test_badges_and_award_retry_concurrency(client):
    headers,uid,config=seed(client)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _:award_completion('routine','morning','test',uid,'2026-10-01'),range(8)))
    assert board(client,uid)['earned']==2
    for n in range(2,6):award_completion('routine','morning','test',uid,f'2026-10-0{n}')
    assert board(client,uid)['badges'][0]['earned'] is True


def test_role_csrf_validation_and_midnight(client):
    headers,uid,config=seed(client);day=client.get('/api/family/rewards').json()['today']
    assert client.put(f'/api/family/rewards/{uid}',json=config).status_code==403
    assert client.put(f'/api/family/rewards/{uid}',headers=headers,json={**config,'rules':config['rules']*2}).status_code==422
    assert client.put(f'/api/family/rewards/{uid}',headers=headers,json={**config,'rules':[{'kind':'medication','source':'pill','label':'Pill','stars':1}]}).status_code==422
    assert client.post(f'/api/family/rewards/{uid}/complete',headers=headers,json={'source':'trash','day':'1990-01-01'}).status_code==409
    wall=login(client,'wall_display')
    assert client.get('/api/family/rewards').status_code==200
    assert client.put(f'/api/family/rewards/{uid}',headers=wall,json=config).status_code==403
    assert client.post(f'/api/family/rewards/{uid}/complete',headers=wall,json={'source':'trash','day':day}).status_code==200
    assert client.post(f'/api/family/rewards/{uid}/complete',headers=wall,json={'source':'unknown','day':day}).status_code==404
    assert client.post(f'/api/family/rewards/{uid}/redeem',headers=wall,json={'goal':config['goal'],'target':3}).status_code==403
    child=login(client,'child')
    assert client.post(f'/api/family/rewards/{uid}/complete',headers=child,json={'source':'trash','day':day}).status_code==403
    assert client.post(f'/api/family/rewards/{uid}/redeem',headers=child,json={'goal':config['goal'],'target':3}).status_code==403
    client.cookies.clear();assert client.get('/api/family/rewards').status_code==401


def test_wellbeing_shared_self_and_wall(client):
    headers,uid,_=seed(client)
    own=client.get('/api/auth/me').json()['user_id']
    day=client.get('/api/family/wellbeing').json()['today']
    data={'day':day,'mood':'okay','energy':'empty','shared':True}
    assert client.put(f'/api/family/wellbeing/{own}',headers=headers,json={**data,'shared':False}).status_code==422
    assert client.put(f'/api/family/wellbeing/{own}',headers=headers,json=data).status_code==200
    wall=login(client,'wall_display')
    assert next(p for p in client.get('/api/family/wellbeing').json()['people'] if p['user_id']==own)['check_in']['energy']=='empty'
    assert client.put(f'/api/family/wellbeing/{own}',headers=wall,json=data).status_code==200
    assert client.put(f'/api/family/wellbeing/{uid}',headers=wall,json=data).status_code==200
    assert client.put(f'/api/family/wellbeing/{uid}',json=data).status_code==403
    assert client.put(f'/api/family/wellbeing/{uid}',headers=wall,json={**data,'mood':'inferred'}).status_code==422
    assert client.put(f'/api/family/wellbeing/{uid}',headers=wall,json={**data,'day':'1990-01-01'}).status_code==409
    with patch('app.family_progress.today',return_value=date(2030,1,1)):
        assert all(p['check_in'] is None for p in client.get('/api/family/wellbeing').json()['people'])


def test_deleted_person_removes_progress(client):
    headers,uid,_=seed(client)
    award_completion('routine','morning','test',uid)
    auth_service.delete_user(uid)
    with connect() as c:
        for table in ['family_reward_settings','family_reward_events','family_reward_redemptions','family_wellbeing']:
            assert c.execute(f'SELECT COUNT(*) FROM {table} WHERE user_id=?',(uid,)).fetchone()[0]==0


def test_routine_hook_awards_only_final_step_and_not_reset(client,tmp_path,monkeypatch):
    from app import routines
    from app.routines import RoutineStore
    headers,uid,_=seed(client)
    monkeypatch.setattr(routines,'routine_store',RoutineStore(tmp_path/'progress.json'))
    snapshot=client.get('/api/family/routines',params={'person_id':uid}).json()
    for index in range(snapshot['routines']['morning']['total']):
        response=client.post('/api/family/routines/morning/complete',headers=headers,json={'person_id':uid,'expected_index':index})
        assert response.status_code==200,response.text
        assert board(client,uid)['earned']==(2 if index==snapshot['routines']['morning']['total']-1 else 0)
    client.post('/api/family/routines/morning/reset',headers=headers,json={'person_id':uid})
    assert board(client,uid)['earned']==2


def test_task_hook_needs_live_unfinished_source_and_success(client,monkeypatch):
    from app.family_tasks import FamilyTasksService,HomeAssistantTasksClient
    from test_family_tasks_v012 import settings
    from app.family_task_assignments import FamilyTaskAssignmentStore
    import json
    headers,uid,config=seed(client)
    key=json.dumps(['familieopgaver','trash'],separators=(',',':'))
    config['rules'].append({'kind':'task','source':key,'label':'Skrald via HA','stars':1})
    assert client.put(f'/api/family/rewards/{uid}',headers=headers,json=config).status_code==200
    service=FamilyTasksService(settings_loader=settings,assignment_store=FamilyTaskAssignmentStore(),people_loader=lambda:[])
    monkeypatch.setattr(service,'get_tasks',lambda user:{'status':'ok'})
    monkeypatch.setattr(HomeAssistantTasksClient,'fetch',lambda self:([{'key':'familieopgaver','items':[{'uid':'trash'}]}],0))
    monkeypatch.setattr(HomeAssistantTasksClient,'complete',lambda *args:None)
    service.complete_task('familieopgaver','trash',{'role':'adult','user_id':'actor'})
    assert board(client,uid)['balance']==1
    monkeypatch.setattr(HomeAssistantTasksClient,'fetch',lambda self:([{'key':'familieopgaver','items':[]}],0))
    with patch('app.family_progress.today',return_value=date(2030,1,1)):
        service.complete_task('familieopgaver','trash',{'role':'adult','user_id':'actor'})
    assert board(client,uid)['balance']==1
    monkeypatch.setattr(HomeAssistantTasksClient,'fetch',lambda self:([{'key':'familieopgaver','items':[{'uid':'trash'}]}],0))
    def fail(*args): raise RuntimeError('HA unavailable')
    monkeypatch.setattr(HomeAssistantTasksClient,'complete',fail)
    with pytest.raises(RuntimeError),patch('app.family_progress.today',return_value=date(2030,1,1)):
        service.complete_task('familieopgaver','trash',{'role':'adult','user_id':'actor'})
    assert board(client,uid)['balance']==1


def test_redemption_serializes_two_adult_clicks(client):
    from app.family_progress import redeem,ExpectedGoal
    from fastapi import HTTPException
    headers,uid,config=seed(client)
    award_completion('routine','morning','test',uid)
    day=client.get('/api/family/rewards').json()['today']
    client.post(f'/api/family/rewards/{uid}/complete',headers=headers,json={'source':'trash','day':day})
    def attempt(_):
        try:
            redeem(uid,ExpectedGoal(goal=config['goal'],target=3),{'user_id':'actor','role':'adult'})
            return 200
        except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(attempt,range(2)))==[200,409]
    assert board(client,uid)['balance']==0


def test_child_own_chore_and_daily_check_in(client):
    headers,uid,config=seed(client)
    assert client.post('/api/auth/login',json={'username':'kid','password':'Progress-Test-Password-123!'}).status_code==200
    headers={'X-CSRF-Token':client.get('/api/auth/me').json()['csrf_token']}
    day=client.get('/api/family/rewards').json()['today']
    assert client.post(f'/api/family/rewards/{uid}/complete',headers=headers,json={'source':'trash','day':day}).status_code==200
    assert client.put(f'/api/family/wellbeing/{uid}',headers=headers,json={'day':day,'mood':'good','energy':'low','shared':True}).status_code==200
    assert client.delete(f'/api/family/wellbeing/{uid}',headers=headers).status_code==200
    assert board(client,uid)['balance']==1


def test_family_visibility_and_disabled_accounts(client):
    headers=login(client,'owner')
    assert client.get('/api/family/rewards').json()['people']==[]
    assert client.get('/api/family/wellbeing').json()['people']==[]
    uid=auth_service.create_user('hiddenkid','Hidden','child','Progress-Test-Password-123!')['user_id']
    auth_service.update_profile(uid,'blue',False)
    assert client.get('/api/family/wellbeing').json()['people']==[]
    auth_service.update_profile(uid,'blue',True)
    assert len(client.get('/api/family/wellbeing').json()['people'])==1


def test_quick_check_in_partial_values_and_legacy_private_answer(client):
    headers,uid,_=seed(client)
    day=client.get('/api/family/wellbeing').json()['today']
    def value():
        return next(p for p in client.get('/api/family/wellbeing').json()['people'] if p['user_id']==uid)['check_in']
    assert client.put(f'/api/family/wellbeing/{uid}',headers=headers,json={'day':day,'mood':'good'}).status_code==200
    assert value()['mood']=='good' and value()['energy'] is None
    assert client.put(f'/api/family/wellbeing/{uid}',headers=headers,json={'day':day,'energy':'empty'}).status_code==200
    assert value()['mood']=='good' and value()['energy']=='empty'
    # Legacy private rows stay hidden; a new shared choice does not expose the old counterpart.
    own=client.get('/api/auth/me').json()['user_id']
    with connect() as c:
        c.execute('INSERT INTO family_wellbeing VALUES(?,?,?,?,?,?,?)',(own,day,'hard','low',0,own,'legacy'))
    assert next(p for p in client.get('/api/family/wellbeing').json()['people'] if p['user_id']==own)['check_in'] is None
    wall=login(client,'wall_display')
    assert next(p for p in client.get('/api/family/wellbeing').json()['people'] if p['user_id']==own)['check_in'] is None
    assert client.put(f'/api/family/wellbeing/{own}',headers=wall,json={'day':day,'mood':'okay'}).status_code==200
    row=next(p for p in client.get('/api/family/wellbeing').json()['people'] if p['user_id']==own)['check_in']
    assert row['shared']==1 and row['mood']=='okay' and row['energy'] is None


def test_quick_check_in_no_guessed_values_or_blank_submission(client):
    headers,uid,_=seed(client)
    day=client.get('/api/family/wellbeing').json()['today']
    for payload in [{'day':day},{'day':day,'mood':None},{'day':day,'shared':True}]:
        assert client.put(f'/api/family/wellbeing/{uid}',headers=headers,json=payload).status_code==422
    assert client.put(f'/api/family/wellbeing/{uid}',headers=headers,json={'day':day,'energy':'high'}).status_code==200
    row=next(p for p in client.get('/api/family/wellbeing').json()['people'] if p['user_id']==uid)['check_in']
    assert row['mood'] is None and row['energy']=='high'


def test_concurrent_quick_choices_merge_on_server(client):
    from app.family_progress import check_in,CheckIn
    headers,uid,_=seed(client)
    day=client.get('/api/family/wellbeing').json()['today']
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda change:check_in(uid,CheckIn(day=day,**change),{'role':'wall_display','user_id':'screen'}),[{'mood':'okay'},{'energy':'low'}]))
    row=next(p for p in client.get('/api/family/wellbeing').json()['people'] if p['user_id']==uid)['check_in']
    assert (row['mood'],row['energy'])==('okay','low')
