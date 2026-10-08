"""Shared reward ledger and voluntary daily mood/energy check-ins."""
import json
from contextlib import closing
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.db import connect
from app.pets import family, editor, today
from app.auth.dependencies import require_csrf

router = APIRouter(prefix='/api/family', tags=['family-progress'])


def initialize_progress(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS family_reward_settings (user_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    conn.execute('''CREATE TABLE IF NOT EXISTS family_reward_events (user_id TEXT NOT NULL, kind TEXT NOT NULL,
        source TEXT NOT NULL, day TEXT NOT NULL, stars INTEGER NOT NULL, label TEXT NOT NULL,
        actor TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(user_id,kind,source,day))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS family_reward_redemptions (id INTEGER PRIMARY KEY,
        user_id TEXT NOT NULL, goal TEXT NOT NULL, stars INTEGER NOT NULL, created_at TEXT NOT NULL, actor TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS family_wellbeing (user_id TEXT NOT NULL, day TEXT NOT NULL,
        mood TEXT NOT NULL, energy TEXT NOT NULL, shared INTEGER NOT NULL, actor TEXT NOT NULL,
        updated_at TEXT NOT NULL, PRIMARY KEY(user_id,day))''')


def people(conn):
    return [dict(r) for r in conn.execute("SELECT user_id,display_name,role FROM auth_users WHERE disabled=0 AND family_visible=1 AND role IN ('owner','adult','child') ORDER BY display_name")]


def person(conn, user_id):
    found = next((p for p in people(conn) if p['user_id'] == user_id), None)
    if not found:
        raise HTTPException(422, 'Vælg et aktivt familiemedlem')
    return found


class Rule(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: Literal['routine', 'task', 'chore']
    source: str = Field(min_length=1, max_length=500)
    label: str = Field(min_length=1, max_length=120)
    stars: int = Field(ge=1, le=20, strict=True)

    @model_validator(mode='after')
    def source_valid(self):
        if self.kind == 'routine' and self.source not in {'morning','evening'}:
            raise ValueError('Vælg morgen- eller aftenrutine')
        if self.kind == 'task':
            key = json.loads(self.source)
            if not isinstance(key,list) or len(key)!=2 or any(not isinstance(v,str) or not v or len(v)>200 for v in key):
                raise ValueError('Ugyldig opgave')
            self.source = json.dumps(key, ensure_ascii=False, separators=(',',':'))
        return self


class RewardSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    goal: str = Field(min_length=1, max_length=120)
    target: int = Field(ge=1, le=1000, strict=True)
    rules: list[Rule] = Field(default_factory=list, max_length=40)

    @model_validator(mode='after')
    def unique_sources(self):
        keys=[(r.kind,r.source) for r in self.rules]
        if len(keys)!=len(set(keys)):
            raise ValueError('Samme gennemførelse kan kun have én regel')
        return self


class ExpectedGoal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    goal: str
    target: int


class ChoreDone(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: str = Field(min_length=1,max_length=500)
    day: str


class CheckIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    day: str
    mood: Literal['good','okay','hard']
    energy: Literal['high','low','empty']
    shared: bool = True


def settings(conn, uid):
    row=conn.execute('SELECT payload FROM family_reward_settings WHERE user_id=?',(uid,)).fetchone()
    return json.loads(row['payload']) if row else None


def ledger(conn, uid):
    earned=conn.execute('SELECT COALESCE(SUM(stars),0) FROM family_reward_events WHERE user_id=?',(uid,)).fetchone()[0]
    spent=conn.execute('SELECT COALESCE(SUM(stars),0) FROM family_reward_redemptions WHERE user_id=?',(uid,)).fetchone()[0]
    return earned, spent


def has_task_reward(source):
    with closing(connect()) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='family_reward_settings'").fetchone():
            return False
        return any(rule['kind']=='task' and rule['source']==source
            for row in conn.execute('SELECT payload FROM family_reward_settings')
            for rule in json.loads(row['payload'])['rules'])


def award_completion(kind, source, actor, user_id=None, day=None):
    """Called only after a successful existing routine/task action, never by a credit API."""
    day = day or today().isoformat()
    with closing(connect()) as conn, conn:
        # Legacy service tests/installations without this additive schema have no reward rules.
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='family_reward_settings'").fetchone():
            return
        eligible={p['user_id'] for p in people(conn)}
        for row in conn.execute('SELECT user_id,payload FROM family_reward_settings').fetchall():
            uid=row['user_id']
            if uid not in eligible or (user_id is not None and uid!=user_id):
                continue
            for rule in json.loads(row['payload'])['rules']:
                if rule['kind']==kind and rule['source']==source:
                    conn.execute('INSERT OR IGNORE INTO family_reward_events VALUES(?,?,?,?,?,?,?,?)',
                        (uid,kind,source,day,rule['stars'],rule['label'],actor,datetime.now(timezone.utc).isoformat()))


@router.get('/rewards')
def rewards(user=Depends(family)):
    with closing(connect()) as conn:
        result=[]
        for p in people(conn):
            earned,spent=ledger(conn,p['user_id'])
            events=[dict(r) for r in conn.execute('SELECT kind,source,day,stars,label FROM family_reward_events WHERE user_id=? ORDER BY day DESC,created_at DESC LIMIT 100',(p['user_id'],))]
            counts={r['kind']:r['n'] for r in conn.execute('SELECT kind,COUNT(*) AS n FROM family_reward_events WHERE user_id=? GROUP BY kind',(p['user_id'],))}
            mornings=conn.execute("SELECT COUNT(*) FROM family_reward_events WHERE user_id=? AND kind='routine' AND source='morning'",(p['user_id'],)).fetchone()[0]
            result.append({**p,'settings':settings(conn,p['user_id']),'earned':earned,'spent':spent,'balance':earned-spent,'events':events,
                'badges':[{'name':'Morgenmester','progress':mornings,'target':5,'earned':mornings>=5},
                    {'name':'Hjælpsom hånd','progress':counts.get('task',0)+counts.get('chore',0),'target':10,'earned':counts.get('task',0)+counts.get('chore',0)>=10}]})
    return {'today':today().isoformat(),'people':result,'can_manage':user['role'] in {'owner','adult'},'can_complete':user['role'] in {'owner','adult','child'},'self_id':user['user_id'],'role':user['role']}


@router.put('/rewards/{user_id}')
def save_rewards(user_id:str,payload:RewardSettings,user=Depends(editor)):
    with closing(connect()) as conn, conn:
        person(conn,user_id)
        conn.execute('INSERT INTO family_reward_settings VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload',(user_id,payload.model_dump_json()))
    return {'ok':True}


@router.post('/rewards/{user_id}/complete')
def complete_chore(user_id:str,payload:ChoreDone,user=Depends(require_csrf)):
    if user['role'] not in {'owner','adult','child'} or (user['role']=='child' and user['user_id']!=user_id):
        raise HTTPException(403,'Denne person kan ikke registreres fra din konto')
    if payload.day!=today().isoformat():
        raise HTTPException(409,'Opdatér til dagens tavle')
    with closing(connect()) as conn, conn:
        person(conn,user_id)
        config=settings(conn,user_id)
        rule=next((r for r in (config or {}).get('rules',[]) if r['kind']=='chore' and r['source']==payload.source),None)
        if not rule: raise HTTPException(404,'Opgaven findes ikke')
        conn.execute('INSERT OR IGNORE INTO family_reward_events VALUES(?,?,?,?,?,?,?,?)',(user_id,'chore',payload.source,payload.day,rule['stars'],rule['label'],user['user_id'],datetime.now(timezone.utc).isoformat()))
    return {'ok':True}


@router.post('/rewards/{user_id}/redeem')
def redeem(user_id:str,payload:ExpectedGoal,user=Depends(editor)):
    with closing(connect()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        person(conn,user_id)
        config=settings(conn,user_id)
        if not config or (config['goal'],config['target'])!=(payload.goal,payload.target):
            raise HTTPException(409,'Målet er ændret; opdatér tavlen')
        earned,spent=ledger(conn,user_id)
        if earned-spent<config['target']: raise HTTPException(409,'Der mangler stjerner til belønningen')
        conn.execute('INSERT INTO family_reward_redemptions(user_id,goal,stars,created_at,actor) VALUES(?,?,?,?,?)',(user_id,config['goal'],config['target'],datetime.now(timezone.utc).isoformat(),user['user_id']))
    return {'ok':True}


@router.get('/wellbeing')
def wellbeing(user=Depends(family)):
    with closing(connect()) as conn:
        result=[]
        for p in people(conn):
            r=conn.execute('SELECT mood,energy,shared,updated_at FROM family_wellbeing WHERE user_id=? AND day=?',(p['user_id'],today().isoformat())).fetchone()
            visible=r is not None and (r['shared'] or p['user_id']==user['user_id'])
            can_write=(user['role']=='wall_display' and (r is None or r['shared'])) or p['user_id']==user['user_id'] or (user['role'] in {'owner','adult'} and p['role']=='child')
            result.append({**p,'check_in':dict(r) if visible else None,'can_write':can_write})
    return {'today':today().isoformat(),'people':result,'shared_only':user['role']=='wall_display'}


@router.put('/wellbeing/{user_id}')
def check_in(user_id:str,payload:CheckIn,user=Depends(require_csrf)):
    if payload.day!=today().isoformat(): raise HTTPException(409,'Opdatér til dagens dato')
    with closing(connect()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        p=person(conn,user_id)
        old=conn.execute('SELECT shared FROM family_wellbeing WHERE user_id=? AND day=?',(user_id,payload.day)).fetchone()
        allowed=p['user_id']==user['user_id'] or (user['role'] in {'owner','adult'} and p['role']=='child') or (user['role']=='wall_display' and payload.shared and (old is None or old['shared']))
        if not allowed: raise HTTPException(403,'Denne dagsform kræver personens egen konto')
        conn.execute('DELETE FROM family_wellbeing WHERE user_id=? AND day<>?',(user_id,payload.day))
        conn.execute('INSERT INTO family_wellbeing VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id,day) DO UPDATE SET mood=excluded.mood,energy=excluded.energy,shared=excluded.shared,actor=excluded.actor,updated_at=excluded.updated_at',(user_id,payload.day,payload.mood,payload.energy,int(payload.shared),user['user_id'],datetime.now(timezone.utc).isoformat()))
    return {'ok':True}


@router.delete('/wellbeing/{user_id}')
def remove_check_in(user_id:str,user=Depends(require_csrf)):
    with closing(connect()) as conn, conn:
        p=person(conn,user_id)
        if user_id!=user['user_id'] and not (user['role'] in {'owner','adult'} and p['role']=='child'):
            raise HTTPException(403,'Kun egen dagsform kan fjernes')
        conn.execute('DELETE FROM family_wellbeing WHERE user_id=? AND day=?',(user_id,today().isoformat()))
    return {'ok':True}
