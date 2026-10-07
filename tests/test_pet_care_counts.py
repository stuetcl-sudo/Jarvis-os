from datetime import date
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.db import connect, init_db
from test_pets import client, login, create

BASE='/api/family/pets'


@pytest.mark.parametrize('role',['adult','child'])
def test_multiple_care_entries_and_undo_are_isolated_and_idempotent(client,role):
    owner=login(client,'owner');pet=create(client,owner);other=create(client,owner)
    headers=login(client,role);day=client.get(BASE).json()['today']
    url=f'{BASE}/{pet}/care/walk/entries';body={'day':day,'request_id':str(uuid4())}
    assert client.post(url,json=body).status_code==403
    one=client.post(url,headers=headers,json=body).json()['id']
    assert client.post(url,headers=headers,json=body).json()['id']==one
    for task in ['walk','food','food','water','water']:
        assert client.post(f'{BASE}/{pet}/care/{task}/entries',headers=headers,json={'day':day,'request_id':str(uuid4())}).status_code==201
    saved=client.get(BASE).json()['pets'][0]
    assert saved['care_counts']=={'food':2,'water':2,'walk':2}
    assert len(saved['care_entries'])==6
    assert client.delete(f'{BASE}/{other}/care/entries/{one}',headers=headers).status_code==404
    assert client.delete(f'{BASE}/{pet}/care/entries/{one}',headers=headers).status_code==200
    assert client.delete(f'{BASE}/{pet}/care/entries/{one}',headers=headers).status_code==200
    # A late retry of the original request cannot recreate an undone entry.
    assert client.post(url,headers=headers,json=body).json()['id']==one
    assert client.get(BASE).json()['pets'][0]['care_counts']['walk']==1
    init_db()
    assert client.get(BASE).json()['pets'][0]['care_counts']['food']==2


def test_care_migration_and_midnight_guard(client):
    h=login(client,'owner');pet=create(client,h)
    with connect() as conn:
        conn.execute('INSERT INTO pet_care VALUES (?,?,?,?)',(pet,'2026-10-07','food','2026-10-07T08:00:00+02:00'));conn.commit()
    init_db();init_db()
    with patch('app.pets.today',return_value=date(2026,10,7)):
        saved=client.get(BASE).json()['pets'][0]
        assert saved['care_counts']['food']==1
        entry=saved['care_entries'][0]['id']
    with patch('app.pets.today',return_value=date(2026,10,8)):
        assert client.get(BASE).json()['pets'][0]['care_counts']=={'food':0,'water':0,'walk':0}
        assert client.delete(f'{BASE}/{pet}/care/entries/{entry}',headers=h).status_code==409
        assert client.post(f'{BASE}/{pet}/care/food/entries',headers=h,json={'day':'2026-10-07','request_id':str(uuid4())}).status_code==409
    assert client.delete(f'{BASE}/{pet}',headers=h).status_code==200
    with connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM pet_care_entries').fetchone()[0]==0


def test_care_display_cannot_write_and_invalid_input_rejected(client):
    h=login(client,'owner');pet=create(client,h);day=client.get(BASE).json()['today']
    body={'day':day,'request_id':str(uuid4())}
    assert client.post(f'{BASE}/{pet}/care/walk/entries',headers=h,json={**body,'request_id':'invalid'}).status_code==422
    assert client.post(f'{BASE}/{pet}/care/madeup/entries',headers=h,json=body).status_code==422
    h=login(client,'wall_display')
    assert client.post(f'{BASE}/{pet}/care/walk/entries',headers=h,json=body).status_code==403
