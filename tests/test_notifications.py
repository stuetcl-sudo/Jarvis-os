import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from test_pets import client, login
from app import notifications as n, config
from app.auth.service import auth_service
from app.db import connect, init_db

BASE='/api/family/notifications'
NOW=datetime.fromisoformat('2026-10-09T08:00:00+02:00')


def subscription(suffix='one'):
    key=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
    return {'endpoint':'https://web.push.apple.com/'+suffix,'keys':{'p256dh':n.encode64(key),'auth':n.encode64(b'0123456789abcdef')}}


def setup(client,monkeypatch,repeat=30):
    monkeypatch.setattr(config,'PUSH_DELIVERY_ENABLED',True)
    owner=login(client,'owner');uid=client.get('/api/auth/me').json()['user_id']
    assert client.put(BASE+'/config',headers=owner,json={'enabled':True,'contact':'mailto:owner@example.org'}).status_code==200
    body={'user_id':uid,'name':'Synthetic medicine','start_date':'2026-01-01','times':['08:00','20:00']}
    pid=client.post('/api/family/medication',headers=owner,json=body).json()['id']
    device={'subscription':subscription(),'name':'Testtelefon','preferences':{'person_ids':[uid],'repeat_minutes':repeat,'quiet_start':'22:00','quiet_end':'07:00'}}
    response=client.post(BASE+'/devices',headers=owner,json=device)
    assert response.status_code==201,response.text
    return owner,uid,pid,response.json()['id'],device


def test_pwa_public_assets_and_no_api_cache(client):
    manifest=client.get('/manifest.webmanifest');assert manifest.status_code==200
    assert manifest.json()['display']=='standalone'
    for icon in manifest.json()['icons']:
        assert client.get(icon['src']).content.startswith(b'\x89PNG')
    worker=client.get('/sw.js');assert worker.headers['service-worker-allowed']=='/'
    assert 'caches.open' not in worker.text and 'fetch(event.request)' in worker.text
    assert client.get(BASE).status_code==401
    owner=login(client,'owner')
    assert client.get(BASE).headers['cache-control']=='no-store'
    assert '<link rel="manifest"' in client.get('/').text
    assert 'data-family-card="notifications"' in client.get('/').text
    child=login(client,'child')
    assert client.get(BASE).status_code==403
    assert client.post(BASE+'/devices',headers=child,json={}).status_code==403
    assert 'data-family-card="notifications"' not in client.get('/').text


def test_opt_in_role_csrf_secrets_and_device_ownership(client,monkeypatch):
    headers,uid,pid,did,device=setup(client,monkeypatch)
    data=client.get(BASE).json();assert len(n.decode64(data['public_key']))==65
    assert client.post(BASE+'/devices',json=device).status_code==403
    assert client.put(BASE+'/config',json={'enabled':False,'contact':'mailto:a@example.org'}).status_code==403
    assert client.post(BASE+'/devices',headers=headers,json=device).json()['id']==did
    init_db();assert client.get(BASE).json()['devices'][0]['id']==did
    with connect() as conn:
        raw=conn.execute('SELECT subscription FROM push_devices').fetchone()[0]
        assert device['subscription']['endpoint'] not in raw
        assert conn.execute("SELECT encrypted_value FROM app_secrets WHERE key='push.vapid.private'").fetchone()
    for forbidden in ['PRIVATE KEY','endpoint','p256dh','auth"','password_hash']:
        assert forbidden not in client.get(BASE).text
    adult=login(client,'adult')
    assert client.get(BASE).json()['devices']==[]
    assert 'contact' not in client.get(BASE).json()
    assert client.put(BASE+'/config',headers=adult,json={'enabled':True,'contact':'mailto:a@example.org'}).status_code==403
    assert client.delete(f'{BASE}/devices/{did}',headers=adult).status_code==404
    assert client.post(f'{BASE}/devices/{did}/test',headers=adult).status_code==404
    assert client.post(BASE+'/devices',headers=adult,json=device).status_code==409


@pytest.mark.parametrize('endpoint',['http://web.push.apple.com/a','https://127.0.0.1/a','https://localhost/a','https://fcm.googleapis.com.evil.example/a','https://evil.example/a','https://user:pass@web.push.apple.com/a','https://web.push.apple.com:8443/a','https://web.push.apple.com/a#secret','https://web.push.apple.com\\@evil.example/a'])
def test_reject_push_ssrf_urls(client,monkeypatch,endpoint):
    headers,_,_,_,device=setup(client,monkeypatch)
    device['subscription']['endpoint']=endpoint
    assert client.post(BASE+'/devices',headers=headers,json=device).status_code==422


def test_real_encryption_sender_timeout_no_redirect_and_expiry(client,monkeypatch):
    _,_,_,did,_=setup(client,monkeypatch)
    with connect() as conn: device=dict(conn.execute('SELECT * FROM push_devices WHERE id=?',(did,)).fetchone())
    payload={'title':'Test','body':'Test','url':'/#medicin'}
    response=requests.Response();response.status_code=201;response._content=b''
    with patch('requests.Session.post',return_value=response) as post:
        assert n.send_push(device,payload)=='sent'
        args=post.call_args
        assert args.kwargs['allow_redirects'] is False and args.kwargs['timeout']==5
        assert args.kwargs['headers']['content-encoding']=='aes128gcm'
        assert 'authorization' in {key.lower() for key in args.kwargs['headers']}
        assert isinstance(args.kwargs['data'],bytes) and b'Test' not in args.kwargs['data']
    for code,state in [(410,'expired'),(404,'expired'),(429,'retry'),(503,'retry'),(302,'rejected'),(403,'rejected')]:
        response.status_code=code
        with patch('requests.Session.post',return_value=response): assert n.send_push(device,payload)==state


def test_persistent_dedup_single_repeat_and_taken_cancels(client,monkeypatch):
    headers,uid,pid,did,_=setup(client,monkeypatch)
    sent=[];sender=lambda d,p:(sent.append(p) or 'sent')
    n.run_notifications_once(NOW-timedelta(minutes=1),sender);assert sent==[]
    for _ in range(3):n.run_notifications_once(NOW,sender)
    assert len(sent)==1 and 'Synthetic medicine' not in sent[0]['body']
    init_db();n.run_notifications_once(NOW+timedelta(minutes=29),sender);assert len(sent)==1
    n.run_notifications_once(NOW+timedelta(minutes=30),sender);assert len(sent)==2
    assert sent[0]['tag']==sent[1]['tag']
    n.run_notifications_once(NOW+timedelta(minutes=60),sender);assert len(sent)==2
    with connect() as conn:
        row=conn.execute('SELECT revision FROM medication_plans WHERE id=?',(pid,)).fetchone()
    with patch('app.medication.today',return_value=NOW.date()):
        assert client.put(f'/api/family/medication/{pid}/record',headers=headers,json={'revision':row['revision'],'day':str(NOW.date()),'slot':'08:00','status':'taken'}).status_code==200
    n.run_notifications_once(NOW+timedelta(minutes=90),sender);assert len(sent)==2
    with connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM push_deliveries').fetchone()[0]==2


def test_taken_before_first_push_and_skipped_cancel(client,monkeypatch):
    _,_,pid,_,_=setup(client,monkeypatch)
    for status in ['taken','skipped']:
        with connect() as conn:
            conn.execute("INSERT OR REPLACE INTO medication_records VALUES (?,?,?,?,?,?,?)",(pid,str(NOW.date()),'08:00',status,NOW.isoformat(),'test','{}'))
        sent=[];n.run_notifications_once(NOW,lambda d,p:(sent.append(p) or 'sent'))
        assert sent==[]


def test_quiet_hours_empty_selection_disabled_and_bounded_backlog(client,monkeypatch):
    headers,_,_,_,device=setup(client,monkeypatch)
    sent=[];sender=lambda d,p:(sent.append(p) or 'sent')
    for changed in [{'person_ids':[]},{'medication':False},{'quiet_start':'07:00','quiet_end':'10:00'},{'quiet_start':'08:00','quiet_end':'09:00'}]:
        client.post(BASE+'/devices',headers=headers,json={**device,'preferences':{**device['preferences'],**changed}})
        n.run_notifications_once(NOW,sender);assert sent==[]
    client.post(BASE+'/devices',headers=headers,json=device)
    n.run_notifications_once(NOW+timedelta(minutes=121),sender);assert sent==[]
    monkeypatch.setattr(config,'PUSH_DELIVERY_ENABLED',False)
    n.run_notifications_once(NOW,sender);assert sent==[]
    monkeypatch.setattr(config,'PUSH_DELIVERY_ENABLED',True)
    client.put(BASE+'/config',headers=headers,json={'enabled':False,'contact':'mailto:a@example.org'})
    n.run_notifications_once(NOW,sender);assert sent==[]
    assert n.in_quiet_hours('23:00','22:00','07:00')
    assert n.in_quiet_hours('06:59','22:00','07:00')
    assert not n.in_quiet_hours('07:00','22:00','07:00')
    assert not n.in_quiet_hours('23:00','22:00','22:00')


def test_late_initial_push_does_not_immediately_send_repeat(client,monkeypatch):
    setup(client,monkeypatch)
    sent=[];sender=lambda d,p:(sent.append(p) or 'sent')
    n.run_notifications_once(NOW+timedelta(minutes=40),sender);assert len(sent)==1
    n.run_notifications_once(NOW+timedelta(minutes=41),sender);assert len(sent)==1
    n.run_notifications_once(NOW+timedelta(minutes=70),sender);assert len(sent)==2


def test_retries_restart_expired_subscription_and_test_rate_limit(client,monkeypatch):
    headers,_,_,did,_=setup(client,monkeypatch)
    attempts=[];sender=lambda d,p:(attempts.append(1) or 'retry')
    for seconds in [0,30,60,120,180,240]:n.run_notifications_once(NOW+timedelta(seconds=seconds),sender)
    assert len(attempts)==3
    with patch.object(n,'send_push',return_value='sent'):
        assert client.post(f'{BASE}/devices/{did}/test',headers=headers).json()['status']=='accepted'
        assert client.post(f'{BASE}/devices/{did}/test',headers=headers).status_code==429
    with connect() as conn:conn.execute('DELETE FROM push_deliveries')
    n.run_notifications_once(NOW,lambda d,p:'expired')
    assert client.get(BASE).json()['devices']==[]


@pytest.mark.parametrize('operation',['logout','disable','reset','delete'])
def test_account_revocation_stops_push(client,monkeypatch,operation):
    headers,uid,_,_,_=setup(client,monkeypatch)
    if operation=='logout':assert client.post('/api/auth/logout',headers=headers).status_code==200
    elif operation=='disable':auth_service.set_user_disabled('owner',True)
    elif operation=='reset':auth_service.reset_password('owner','Changed-Notification-Pass-123!')
    else:
        # Owner deletion is intentionally forbidden; use an adult device instead.
        adult=login(client,'adult');uid=client.get('/api/auth/me').json()['user_id']
        client.post(BASE+'/devices',headers=adult,json={'subscription':subscription('adult'),'preferences':{'person_ids':[uid]}})
        auth_service.delete_user(uid)
    with connect() as conn: assert conn.execute('SELECT COUNT(*) FROM push_devices WHERE user_id=?',(uid,)).fetchone()[0]==0


def test_preference_validation_and_key_stability(client,monkeypatch):
    headers,uid,_,_,device=setup(client,monkeypatch)
    first=client.get(BASE).json()['public_key']
    client.put(BASE+'/config',headers=headers,json={'enabled':True,'contact':'mailto:changed@example.org'})
    assert client.get(BASE).json()['public_key']==first
    for changes in [{'person_ids':['missing']},{'person_ids':[uid,uid]},{'repeat_minutes':2},{'quiet_start':'25:00'}]:
        assert client.post(BASE+'/devices',headers=headers,json={**device,'preferences':{**device['preferences'],**changes}}).status_code==422
    device['subscription']['keys']['auth']='broken'
    assert client.post(BASE+'/devices',headers=headers,json=device).status_code==422


def test_wall_can_manage_own_push_but_not_global_config(client,monkeypatch):
    _,uid,_,_,_=setup(client,monkeypatch)
    headers=login(client,'wall_display')
    response=client.post(BASE+'/devices',headers=headers,json={'subscription':subscription('wall'),'preferences':{'person_ids':[uid]}})
    assert response.status_code==201,response.text
    did=response.json()['id']
    assert len(client.get(BASE).json()['devices'])==1
    assert client.put(BASE+'/config',headers=headers,json={'enabled':False,'contact':'mailto:a@example.org'}).status_code==403
    assert client.delete(f'{BASE}/devices/{did}',headers=headers).status_code==200


def test_expired_test_subscription_is_removed(client,monkeypatch):
    headers,_,_,did,_=setup(client,monkeypatch)
    with patch.object(n,'send_push',return_value='expired'):
        assert client.post(f'{BASE}/devices/{did}/test',headers=headers).status_code==503
    assert client.get(BASE).json()['devices']==[]


def test_live_preferences_replace_payload_before_send(client,monkeypatch):
    _,_,_,did,_=setup(client,monkeypatch)
    with connect() as conn:
        row=conn.execute('SELECT preferences FROM push_devices WHERE id=?',(did,)).fetchone()
        prefs=json.loads(row[0]);prefs['show_details']=True
        conn.execute('UPDATE push_devices SET preferences=? WHERE id=?',(json.dumps(prefs),did))
    original=n.candidates;calls=0
    def change_after_snapshot(conn,device,now):
        nonlocal calls
        calls+=1
        result=original(conn,device,now)
        if calls==1:
            with connect() as update:
                prefs['show_details']=False
                update.execute('UPDATE push_devices SET preferences=? WHERE id=?',(json.dumps(prefs),did))
        return result
    monkeypatch.setattr(n,'candidates',change_after_snapshot)
    sent=[];n.run_notifications_once(NOW,lambda device,payload:(sent.append(payload) or 'sent'))
    assert len(sent)==1 and 'Synthetic medicine' not in sent[0]['body']
