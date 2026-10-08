from datetime import date
from unittest.mock import patch

import pytest

from app.auth.service import auth_service
from app.db import connect, init_db
from test_pets import client, login, create

PETS = '/api/family/pets'
MED = '/api/family/medication'


def test_repeat_month_end_idempotence_and_history(client):
    h = login(client,'adult');pet = create(client,h)
    r = client.post(f'{PETS}/{pet}/reminders',headers=h,json={'title':'Pleje','kind':'other','due_date':'2027-01-31','interval_unit':'months','interval_count':1})
    assert r.status_code == 201, r.text
    rid=r.json()['id'];url=f'{PETS}/{pet}/reminders/{rid}'
    body={'completed':True,'occurrence_date':'2027-01-31'}
    assert client.put(url,headers=h,json=body).status_code == 200
    assert client.put(url,headers=h,json=body).status_code == 409
    assert client.get(PETS).json()['pets'][0]['reminders'][0]['due_date']=='2027-02-28'
    assert client.put(url,headers=h,json={'completed':True,'occurrence_date':'2027-02-28'}).status_code == 200
    assert client.get(PETS).json()['pets'][0]['reminders'][0]['due_date']=='2027-03-31'
    init_db()
    with connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM pet_reminder_history').fetchone()[0]==2
    assert client.delete(url,headers=h).status_code==200
    with connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM pet_reminder_history').fetchone()[0]==0


def test_repeat_year_leap_day_and_range(client):
    h=login(client,'owner');pet=create(client,h)
    r=client.post(f'{PETS}/{pet}/reminders',headers=h,json={'title':'Årligt','kind':'other','due_date':'2024-02-29','interval_unit':'years','interval_count':1}).json()['id']
    for before,after in [('2024-02-29','2025-02-28'),('2025-02-28','2026-02-28'),('2026-02-28','2027-02-28'),('2027-02-28','2028-02-29')]:
        assert client.put(f'{PETS}/{pet}/reminders/{r}',headers=h,json={'completed':True,'occurrence_date':before}).status_code==200
        assert client.get(PETS).json()['pets'][0]['reminders'][0]['due_date']==after
    r=client.post(f'{PETS}/{pet}/reminders',headers=h,json={'title':'Grænse','kind':'other','due_date':'9999-12-31','interval_unit':'days'}).json()['id']
    assert client.put(f'{PETS}/{pet}/reminders/{r}',headers=h,json={'completed':True,'occurrence_date':'9999-12-31'}).status_code==422
    with connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM pet_reminder_history WHERE reminder_id=?',(r,)).fetchone()[0]==0


def test_expenses_persistence_isolation_validation(client):
    h=login(client,'adult');pet=create(client,h);other=create(client,h)
    url=f'{PETS}/{pet}/expenses';body={'day':'2026-01-01','category':'food','title':'Foder','amount_ore':12345}
    assert client.post(url,json=body).status_code==403
    eid=client.post(url,headers=h,json=body).json()['id']
    init_db()
    response=client.get(url);assert response.headers['cache-control']=='no-store'
    assert response.json()['expenses'][0]['amount_ore']==12345
    assert client.get(f'{PETS}/{other}/expenses').json()['expenses']==[]
    assert client.delete(f'{PETS}/{other}/expenses/{eid}',headers=h).status_code==404
    for extra in [{'amount_ore':-1},{'amount_ore':12.3},{'day':'2999-01-01'},{'category':'bank'},{'title':' '}]:
        assert client.post(url,headers=h,json={**body,**extra}).status_code==422
    assert client.delete(f'{PETS}/{pet}',headers=h).status_code==200
    with connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM pet_expenses').fetchone()[0]==0


@pytest.mark.parametrize('role',['child','wall_display'])
def test_medication_and_money_adult_only(client,role):
    owner=login(client,'owner');pet=create(client,owner)
    h=login(client,role)
    assert client.get(f'{PETS}/{pet}/expenses').status_code==403
    assert client.get(MED).status_code==403
    assert client.post(MED,headers=h,json={}).status_code==403
    assert ('data-medication-display="true"' in client.get('/').text) == (role == 'wall_display')


def test_medication_anonymous_and_csrf(client):
    assert client.get(MED).status_code==401
    login(client,'adult')
    person=client.get(MED).json()['people'][0]['user_id']
    body={'user_id':person,'name':'Egen medicin','start_date':'2026-01-01','times':['08:00']}
    assert client.post(MED,json=body).status_code==403
    assert client.get(MED).headers['cache-control']=='no-store'


def test_medication_today_schedule_stale_plan_history_and_delete(client):
    h=login(client,'adult');uid=client.get(MED).json()['people'][0]['user_id']
    body={'user_id':uid,'name':'Egen medicin','instructions':'Min angivne plan','start_date':'2026-01-01','times':['08:00','20:00'],'weekdays':[2]}
    pid=client.post(MED,headers=h,json=body).json()['id'];url=f'{MED}/{pid}'
    with patch('app.medication.today',return_value=date(2026,10,7)):
        plan=client.get(MED).json()['plans'][0];assert plan['due_today']
        record={'revision':plan['revision'],'day':'2026-10-07','slot':'08:00','status':'taken'}
        for _ in range(2):assert client.put(url+'/record',headers=h,json=record).status_code==200
        saved=client.get(MED).json()['plans'][0];assert len(saved['records'])==1
        assert saved['records'][0]['recorded_by']==uid
        assert 'Min angivne plan' in saved['records'][0]['plan_snapshot']
        changed={**body,'revision':plan['revision'],'instructions':'Ny angivet plan'}
        assert client.put(url,headers=h,json=changed).status_code==200
        assert client.put(url,headers=h,json=changed).status_code==409
        assert client.put(url+'/record',headers=h,json=record).status_code==409
        plan=client.get(MED).json()['plans'][0];record['revision']=plan['revision']
        assert client.put(url+'/record',headers=h,json={**record,'slot':'09:00'}).status_code==409
        assert client.put(url+'/record',headers=h,json={**record,'status':'unmarked'}).status_code==200
        assert not client.get(MED).json()['plans'][0]['records']
        assert client.put(url+'/record',headers=h,json=record).status_code==200
    with patch('app.medication.today',return_value=date(2026,10,8)):
        assert not client.get(MED).json()['plans'][0]['due_today']
        assert client.put(url+'/record',headers=h,json=record).status_code==409
    assert client.delete(url,headers=h).status_code==200
    with connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM medication_records').fetchone()[0]==0


def test_medication_validates_person_dates_times_and_user_deletion(client):
    h=login(client,'owner');uid=client.get(MED).json()['people'][0]['user_id']
    body={'user_id':uid,'name':'Egen plan','start_date':'2026-01-01','times':['08:00']}
    for extra in [{'user_id':'missing'},{'times':['25:00']},{'times':['08:00','08:00']},{'weekdays':[7]},{'weekdays':[]},{'end_date':'2025-01-01'}]:
        assert client.post(MED,headers=h,json={**body,**extra}).status_code==422
    child=auth_service.create_user('kid','Barn','child','Pets-Test-Password-123!')
    child_id=next(p['user_id'] for p in client.get(MED).json()['people'] if p['role']=='child')
    r=client.post(MED,headers=h,json={**body,'user_id':child_id});assert r.status_code==201
    auth_service.delete_user(child_id)
    assert not client.get(MED).json()['plans']


def test_old_reminder_schema_migrates_without_data_loss(client):
    h=login(client,'owner');pet=create(client,h)
    with connect() as conn:
        conn.execute('DROP TABLE pet_reminders')
        conn.execute('CREATE TABLE pet_reminders (id INTEGER PRIMARY KEY,pet_id INTEGER,title TEXT,kind TEXT,due_date TEXT,notes TEXT,completed INTEGER DEFAULT 0)')
        conn.execute('INSERT INTO pet_reminders VALUES (1,?,\'Eksisterende\',\'other\',\'2026-10-07\',\'\',0)',(pet,));conn.commit()
    init_db();init_db()
    reminder=client.get(PETS).json()['pets'][0]['reminders'][0]
    assert reminder['title']=='Eksisterende' and reminder['interval_unit']=='none'
