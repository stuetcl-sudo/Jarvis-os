"""Opt-in, server-backed medication Web Push. No HA services or automatic check-off."""
import asyncio
import base64
import hashlib
import json
import re
import threading
import time
from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from py_vapid import Vapid
from pywebpush import webpush, WebPushException

from app import config, settings_store
from app.auth.dependencies import require_csrf, require_owner_csrf
from app.db import connect
from app.home_setup import load_home_settings
from app.medication import display_reader, scheduled
from app.pets import board_editor

router = APIRouter(prefix='/api/family/notifications', tags=['notifications'])
_key_lock = threading.Lock()
_tick_lock = threading.Lock()
MAX_AGE_MINUTES = 120


def initialize_notifications(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS push_devices (
        id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, endpoint_hash TEXT UNIQUE NOT NULL,
        subscription TEXT NOT NULL, name TEXT NOT NULL, preferences TEXT NOT NULL,
        created_at TEXT NOT NULL, test_at REAL NOT NULL DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS push_deliveries (
        device_id INTEGER NOT NULL, event_key TEXT NOT NULL, day TEXT NOT NULL,
        state TEXT NOT NULL, attempts INTEGER NOT NULL, attempted_at REAL NOT NULL,
        PRIMARY KEY(device_id,event_key))''')


def revoke_devices(conn, user_id):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='push_devices'").fetchone():
        conn.execute('DELETE FROM push_deliveries WHERE device_id IN (SELECT id FROM push_devices WHERE user_id=?)', (user_id,))
        conn.execute('DELETE FROM push_devices WHERE user_id=?', (user_id,))


def encode64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def decode64(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}', value):
        raise ValueError('Ugyldig push-nøgle')
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def trusted_endpoint(value):
    try:
        url = urlsplit(value)
        host = (url.hostname or '').lower()
        trusted = host in {'fcm.googleapis.com', 'updates.push.services.mozilla.com'} or host.endswith('.push.apple.com') or host.endswith('.notify.windows.com')
        if not trusted or url.scheme != 'https' or url.username or url.password or url.port not in {None,443} or url.fragment or not url.path or '\\' in value or any(c.isspace() for c in value):
            raise ValueError('Push-adressen tilhører ikke en understøttet push-tjeneste')
    except ValueError:
        raise ValueError('Ugyldig eller ikke understøttet push-adresse')
    return value


class Preferences(BaseModel):
    model_config = ConfigDict(extra='forbid')
    person_ids: list[str] = Field(default_factory=list, max_length=50)
    medication: bool = True
    repeat_minutes: int | None = None
    quiet_start: str = Field(default='22:00', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    quiet_end: str = Field(default='07:00', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    show_details: bool = False

    @field_validator('repeat_minutes')
    @classmethod
    def bounded_repeat(cls, value):
        if value not in {None,15,30,60}: raise ValueError('Vælg ingen gentagelse, 15, 30 eller 60 minutter')
        return value

    @field_validator('person_ids')
    @classmethod
    def unique_people(cls, value):
        if len(set(value)) != len(value) or any(not p or len(p)>100 for p in value): raise ValueError('Ugyldigt personvalg')
        return value


class Subscription(BaseModel):
    model_config = ConfigDict(extra='forbid')
    endpoint: str = Field(max_length=2048)
    expirationTime: float | None = None
    keys: dict[str,str]

    _endpoint = field_validator('endpoint')(trusted_endpoint)

    @field_validator('keys')
    @classmethod
    def valid_keys(cls, value):
        if set(value) != {'p256dh','auth'} or any(len(v)>120 for v in value.values()): raise ValueError('Ugyldige push-nøgler')
        raw = decode64(value['p256dh'])
        if len(raw)!=65 or raw[0]!=4: raise ValueError('Brug en ukomprimeret P-256 push-nøgle')
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)
        if len(decode64(value['auth'])) != 16: raise ValueError('Ugyldig push-auth')
        return value


class Device(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(default='Min telefon', min_length=1, max_length=80)
    subscription: Subscription
    preferences: Preferences


class PushConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    enabled: bool
    contact: str = Field(max_length=200)

    @field_validator('contact')
    @classmethod
    def contact_uri(cls, value):
        if re.fullmatch(r'mailto:[^\s@]+@[^\s@]+\.[^\s@]+',value): return value
        raise ValueError('Brug mailto: efterfulgt af ejerens kontaktmail')


def server_configuration():
    return {'enabled':settings_store.get_setting('push.enabled','false',db_path=config.DB_PATH)=='true',
            'contact':settings_store.get_setting('push.contact','',db_path=config.DB_PATH)}


def vapid_key(create=False):
    with _key_lock:
        private = settings_store.get_secret('push.vapid.private','',db_path=config.DB_PATH)
        if not private and create:
            key = ec.generate_private_key(ec.SECP256R1())
            private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
            encrypted=settings_store._fernet(db_path=config.DB_PATH).encrypt(private.encode()).decode()
            with closing(connect()) as conn, conn:
                conn.execute('INSERT OR IGNORE INTO app_secrets(key,encrypted_value,updated_at) VALUES (?,?,?)',('push.vapid.private',encrypted,datetime.now(timezone.utc).isoformat()))
            private=settings_store.get_secret('push.vapid.private',db_path=config.DB_PATH)
        return serialization.load_pem_private_key(private.encode(),password=None) if private else None


def eligible_people(conn):
    return [dict(r) for r in conn.execute("SELECT user_id,display_name FROM auth_users WHERE disabled=0 AND role IN ('owner','adult','child') ORDER BY display_name")]


@router.get('')
def status(user=Depends(display_reader)):
    cfg=server_configuration(); key=vapid_key()
    with closing(connect()) as conn:
        devices=[{'id':r['id'],'name':r['name'],'preferences':json.loads(r['preferences'])} for r in conn.execute('SELECT id,name,preferences FROM push_devices WHERE user_id=? ORDER BY id',(user['user_id'],))]
        people=eligible_people(conn)
    result={'enabled':cfg['enabled'],'delivery_enabled':config.PUSH_DELIVERY_ENABLED,'public_key':encode64(key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)) if key else None,
            'devices':devices,'people':people,'can_configure':user['role']=='owner','max_age_minutes':MAX_AGE_MINUTES}
    if user['role']=='owner': result['contact']=cfg['contact']
    return result


@router.put('/config')
def configure(payload: PushConfiguration, user=Depends(require_owner_csrf)):
    vapid_key(create=True)
    settings_store.set_setting('push.contact',payload.contact,db_path=config.DB_PATH)
    settings_store.set_setting('push.enabled','true' if payload.enabled else 'false',db_path=config.DB_PATH)
    return {'ok':True}


@router.post('/devices',status_code=201)
def subscribe(payload: Device, user=Depends(board_editor)):
    if not server_configuration()['enabled'] or not vapid_key(): raise HTTPException(409,'Ejeren skal aktivere telefonbeskeder først')
    subscription=payload.subscription.model_dump()
    endpoint_hash=hashlib.sha256(subscription['endpoint'].encode()).hexdigest()
    # Encrypt endpoint and device keys with this installation's existing master key.
    encrypted=settings_store._fernet(db_path=config.DB_PATH).encrypt(json.dumps(subscription).encode()).decode()
    with closing(connect()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        if not set(payload.preferences.person_ids) <= {p['user_id'] for p in eligible_people(conn)}: raise HTTPException(422,'Vælg aktive familiemedlemmer')
        old=conn.execute('SELECT id,user_id FROM push_devices WHERE endpoint_hash=?',(endpoint_hash,)).fetchone()
        if old and old['user_id']!=user['user_id']: raise HTTPException(409,'Denne push-tilmelding tilhører en anden konto. Slå beskeder fra i browseren og tilmeld igen.')
        if not old and conn.execute('SELECT COUNT(*) FROM push_devices WHERE user_id=?',(user['user_id'],)).fetchone()[0]>=10: raise HTTPException(409,'Der kan højst tilmeldes 10 enheder pr. konto')
        conn.execute('''INSERT INTO push_devices(user_id,endpoint_hash,subscription,name,preferences,created_at) VALUES (?,?,?,?,?,?)
            ON CONFLICT(endpoint_hash) DO UPDATE SET subscription=excluded.subscription,name=excluded.name,preferences=excluded.preferences''',
            (user['user_id'],endpoint_hash,encrypted,payload.name,payload.preferences.model_dump_json(),datetime.now(timezone.utc).isoformat()))
        return {'id':conn.execute('SELECT id FROM push_devices WHERE endpoint_hash=?',(endpoint_hash,)).fetchone()[0]}


def own_device(conn, device_id, user):
    row=conn.execute('SELECT * FROM push_devices WHERE id=? AND user_id=?',(device_id,user['user_id'])).fetchone()
    if not row: raise HTTPException(404,'Enheden findes ikke for denne konto')
    return row


@router.delete('/devices/{device_id}')
def unsubscribe(device_id: int, user=Depends(board_editor)):
    with closing(connect()) as conn, conn:
        own_device(conn,device_id,user)
        conn.execute('DELETE FROM push_deliveries WHERE device_id=?',(device_id,))
        conn.execute('DELETE FROM push_devices WHERE id=?',(device_id,))
    return {'ok':True}


class NoRedirectSession(requests.Session):
    def post(self, url, **kwargs):
        trusted_endpoint(url)
        kwargs['allow_redirects']=False
        return super().post(url,**kwargs)


def send_push(device, payload):
    cfg=server_configuration()
    if not cfg['enabled'] or not config.PUSH_DELIVERY_ENABLED: return 'disabled'
    key=vapid_key()
    subscription=json.loads(settings_store._fernet(db_path=config.DB_PATH).decrypt(device['subscription'].encode()))
    trusted_endpoint(subscription['endpoint'])
    with NoRedirectSession() as session:
        session.trust_env=False
        try:
            webpush(subscription_info=subscription,data=json.dumps(payload,ensure_ascii=False),vapid_private_key=Vapid(key),vapid_claims={'sub':cfg['contact']},ttl=300,timeout=5,requests_session=session)
            return 'sent'
        except WebPushException as exc:
            code=exc.response.status_code if exc.response is not None else 0
            if code in {404,410}: return 'expired'
            return 'retry' if code==429 or code>=500 or code==0 else 'rejected'
        except requests.RequestException:
            return 'retry'


@router.post('/devices/{device_id}/test')
def test_device(device_id: int, user=Depends(board_editor)):
    with closing(connect()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        device=dict(own_device(conn,device_id,user)); now=time.time()
        if now-device['test_at']<30: raise HTTPException(429,'Vent 30 sekunder før næste test')
        conn.execute('UPDATE push_devices SET test_at=? WHERE id=?',(now,device_id))
    try: result=send_push(device,{'title':'Jarvis','body':'Test af telefonbeskeder fra Jarvis','tag':'jarvis-test','url':'/#beskeder'})
    except Exception: result='rejected'
    if result=='expired':
        with closing(connect()) as conn, conn:
            conn.execute('DELETE FROM push_deliveries WHERE device_id=?',(device_id,))
            conn.execute('DELETE FROM push_devices WHERE id=?',(device_id,))
    if result!='sent': raise HTTPException(503,'Testen kunne ikke sendes. Kontrollér serverens push-opsætning og enhedens tilladelse.')
    return {'status':'accepted','message':'Push-tjenesten har accepteret testen; kontrollér telefonen.'}


def in_quiet_hours(clock, start, end):
    if start==end: return False
    return start<=clock<end if start<end else clock>=start or clock<end


def candidates(conn, device, now):
    prefs=Preferences.model_validate_json(device['preferences'])
    if not prefs.medication or in_quiet_hours(now.strftime('%H:%M'),prefs.quiet_start,prefs.quiet_end): return []
    day=now.date(); selected=set(prefs.person_ids); result=[]
    for row in conn.execute("SELECT p.*,u.display_name FROM medication_plans p JOIN auth_users u ON u.user_id=p.user_id WHERE u.disabled=0 AND u.role IN ('owner','adult','child')"):
        plan=json.loads(row['plan'])
        if row['user_id'] not in selected or not scheduled(plan,day): continue
        records={r['slot']:r['status'] for r in conn.execute('SELECT slot,status FROM medication_records WHERE plan_id=? AND day=?',(row['id'],day.isoformat()))}
        for slot in plan['times']:
            if records.get(slot) in {'taken','skipped'}: continue
            # Local wall-clock arithmetic: do not send before the scheduled slot.
            age=now.hour*60+now.minute-(int(slot[:2])*60+int(slot[3:]))
            if not 0<=age<=MAX_AGE_MINUTES: continue
            base=f"{row['id']}:{row['revision']}:{day}:{slot}"
            first=conn.execute('SELECT state,attempted_at FROM push_deliveries WHERE device_id=? AND event_key=?',(device['id'],base+':0')).fetchone()
            repeat=prefs.repeat_minutes
            sequence=[0]+([1] if repeat is not None and first and first['state']=='sent' and now.timestamp()-first['attempted_at']>=repeat*60 else [])
            for number in sequence:
                event_key=f'{base}:{number}'
                body=f"{row['display_name']} · {plan['name']} kl. {slot} mangler registrering." if prefs.show_details else f'Medicin kl. {slot} mangler registrering. Åbn Jarvis for at se dagens oversigt.'
                result.append((event_key,{'title':'Jarvis · Medicinpåmindelse','body':body,'tag':'jarvis-med-'+hashlib.sha256(base.encode()).hexdigest()[:24],'url':'/#medicin'}))
    return result


def run_notifications_once(now=None, sender=None):
    """One persistent initial/reminder delivery per device/slot; no HA dependency."""
    if not config.PUSH_DELIVERY_ENABLED or not server_configuration()['enabled']: return
    sender=sender or send_push
    if not _tick_lock.acquire(blocking=False): return
    try:
        local=now or datetime.now(ZoneInfo(load_home_settings(db_path=config.DB_PATH)['timezone']))
        timestamp=local.timestamp()
        with closing(connect()) as conn, conn:
            conn.execute('DELETE FROM push_deliveries WHERE day<?',((local.date().fromordinal(max(1,local.date().toordinal()-7))).isoformat(),))
            # Remove consent when its account disappears/is disabled/changes role.
            conn.execute("DELETE FROM push_deliveries WHERE device_id IN (SELECT d.id FROM push_devices d LEFT JOIN auth_users u ON u.user_id=d.user_id WHERE u.user_id IS NULL OR u.disabled=1 OR u.role NOT IN ('owner','adult','wall_display'))")
            conn.execute("DELETE FROM push_devices WHERE user_id NOT IN (SELECT user_id FROM auth_users WHERE disabled=0 AND role IN ('owner','adult','wall_display'))")
            devices=[dict(r) for r in conn.execute('SELECT * FROM push_devices ORDER BY id')]
        for device in devices:
            with closing(connect()) as conn:
                pending=candidates(conn,device,local)
            for event_key,payload in pending:
                with closing(connect()) as conn, conn:
                    conn.execute('BEGIN IMMEDIATE')
                    # Re-read live preferences and records just before claiming.
                    active=conn.execute("SELECT d.* FROM push_devices d JOIN auth_users u ON u.user_id=d.user_id WHERE d.id=? AND u.disabled=0 AND u.role IN ('owner','adult','wall_display')",(device['id'],)).fetchone()
                    live_candidates=dict(candidates(conn,active,local)) if active else {}
                    if event_key not in live_candidates: continue
                    payload=live_candidates[event_key]
                    previous=conn.execute('SELECT * FROM push_deliveries WHERE device_id=? AND event_key=?',(device['id'],event_key)).fetchone()
                    if previous and (previous['state'] in {'sent','rejected'} or previous['attempts']>=3 or timestamp-previous['attempted_at']<(300 if previous['state']=='sending' else 60)): continue
                    attempts=(previous['attempts'] if previous else 0)+1
                    conn.execute('INSERT INTO push_deliveries VALUES (?,?,?,?,?,?) ON CONFLICT(device_id,event_key) DO UPDATE SET state=excluded.state,attempts=excluded.attempts,attempted_at=excluded.attempted_at',(device['id'],event_key,local.date().isoformat(),'sending',attempts,timestamp))
                    device=dict(active)
                try: state=sender(device,payload)
                except Exception: state='retry'
                with closing(connect()) as conn, conn:
                    conn.execute('UPDATE push_deliveries SET state=? WHERE device_id=? AND event_key=?',(state,device['id'],event_key))
                    if state=='expired':
                        conn.execute('DELETE FROM push_deliveries WHERE device_id=?',(device['id'],))
                        conn.execute('DELETE FROM push_devices WHERE id=?',(device['id'],))
    finally: _tick_lock.release()


async def notification_loop():
    while True:
        await asyncio.sleep(30)
        try: await asyncio.to_thread(run_notifications_once)
        except Exception:
            # Do not leak subscription URLs, encrypted keys or medication in logs.
            import logging
            logging.getLogger(__name__).warning('Notification check failed; retrying next cycle')
