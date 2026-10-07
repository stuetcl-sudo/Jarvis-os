"""Read-only HA energy and camera views with owner-selected entities."""
import json
import math
import os
import re
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import config, settings_store
from app.auth.dependencies import require_owner, require_owner_csrf, require_authenticated_user
from app.home_assistant import HomeAssistantClient, load_home_assistant_connection, HomeAssistantConfigurationError, HomeAssistantUnavailable

router = APIRouter()
ENTITY = re.compile(r"^(sensor|camera)\.[a-z0-9_]+$")
ENERGY = {
    "solar_power": ("Solproduktion nu", "power"),
    "consumption_power": ("Husets forbrug nu", "power"),
    "solar_today": ("Produceret i dag", "energy"),
    "consumption_today": ("Forbrugt i dag", "energy"),
    "import_today": ("Købt fra nettet i dag", "energy"),
    "export_today": ("Solgt til nettet i dag", "energy"),
    "battery": ("Batteri", "percent"),
    "price": ("Strømpris nu", "price"),
    "cost_today": ("Udgift i dag", "money"),
    "revenue_today": ("Salgsindtægt i dag", "money"),
}
KEY = "family.home_modules"
_lock=threading.Lock()
_states_cache={}
_image_cache={}


def adults(user=Depends(require_authenticated_user)):
    if user["role"] not in {"owner","adult"}: raise HTTPException(403,"Adult role required")
    return user


def web_url(value):
    value=value.strip()
    if not value: return ""
    p=urlsplit(value)
    if p.scheme not in {"http","https"} or not p.hostname or p.username or p.password or "\\" in value or any(ord(c)<32 for c in value):
        raise ValueError("Brug en http/https-adresse uden loginoplysninger")
    return value


class CameraConfig(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    name: str=Field(min_length=1,max_length=80)
    entity: str=Field(pattern=r"^camera\.[a-z0-9_]+$")
    live_url: str=Field(default="",max_length=500)
    recordings_url: str=Field(default="",max_length=500)
    @field_validator("live_url","recordings_url")
    @classmethod
    def urls(cls,value): return web_url(value)


class HomeConfig(BaseModel):
    model_config=ConfigDict(extra="forbid")
    energy: dict[str,str]=Field(default_factory=dict)
    cameras: list[CameraConfig]=Field(default_factory=list,max_length=12)
    scrypted_url: str=Field(default="",max_length=500)
    @field_validator("energy")
    @classmethod
    def sensors(cls,value):
        if any(k not in ENERGY or (v and not re.fullmatch(r"sensor\.[a-z0-9_]+",v)) for k,v in value.items()):
            raise ValueError("Ugyldig energisensor")
        return value
    @field_validator("cameras")
    @classmethod
    def unique(cls,value):
        if len({c.entity for c in value})!=len(value): raise ValueError("Kameraer må kun vælges én gang")
        return value
    @field_validator("scrypted_url")
    @classmethod
    def scrypted(cls,value): return web_url(value)


def load_config():
    raw=settings_store.get_setting(KEY,"",db_path=config.DB_PATH)
    return HomeConfig.model_validate_json(raw) if raw else HomeConfig()


def states():
    connection=load_home_assistant_connection()
    if connection is None: raise HomeAssistantUnavailable(response_class="not_configured")
    signature=(config.DB_PATH,connection.base_url,connection.access_value)
    with _lock:
        cached=_states_cache.get(signature)
        if cached and time.monotonic()-cached[0]<20: return cached[1]
    payload=HomeAssistantClient(connection).get_json("/api/states")
    if not isinstance(payload,list): raise HomeAssistantUnavailable()
    result={s['entity_id']:s for s in payload if isinstance(s,dict) and isinstance(s.get('entity_id'),str)}
    with _lock:
        _states_cache.clear(); _states_cache[signature]=(time.monotonic(),result)
    return result


@router.get("/api/admin/home-modules/config")
def get_config(user=Depends(require_owner)):
    return {**load_config().model_dump(),"metrics":[{"key":k,"label":v[0],"type":v[1]} for k,v in ENERGY.items()]}


@router.put("/api/admin/home-modules/config")
def save_config(payload:HomeConfig,user=Depends(require_owner_csrf)):
    settings_store.set_setting(KEY,payload.model_dump_json(),db_path=config.DB_PATH)
    with _lock: _states_cache.clear(); _image_cache.clear()
    return {"ok":True}


@router.get("/api/admin/home-modules/entities")
def entities(user=Depends(require_owner)):
    try: data=states()
    except (HomeAssistantConfigurationError,HomeAssistantUnavailable):
        raise HTTPException(503,"Home Assistant er ikke tilsluttet eller svarer ikke. Kontrollér forbindelsen i Administration.")
    return {"entities":[{"entity":key,"name":str(s.get("attributes",{}).get("friendly_name") or key),"unit":str(s.get("attributes",{}).get("unit_of_measurement") or "")} for key,s in data.items() if ENTITY.fullmatch(key)]}


def metric(key,entity,state):
    label,kind=ENERGY[key]
    result={"key":key,"label":label,"value":None,"unit":"","status":"not_configured" if not entity else "unavailable","updated_at":None}
    if not state: return result
    try: value=float(state.get("state"))
    except (ValueError,TypeError): return result
    if not math.isfinite(value): return result
    unit=str(state.get("attributes",{}).get("unit_of_measurement") or "")
    valid=False
    if kind=="power" and unit in {"W","kW"}: valid=True; value=value/1000 if unit=="W" else value; unit="kW"
    elif kind=="energy" and unit in {"Wh","kWh"}: valid=True; value=value/1000 if unit=="Wh" else value; unit="kWh"
    elif kind=="percent" and unit=="%" and 0<=value<=100: valid=True
    elif kind=="price" and unit in {"DKK/kWh","kr/kWh","EUR/kWh","DKK/Wh","kr/Wh","EUR/Wh"}:
        valid=True
        if unit.endswith('/Wh'): value*=1000; unit=unit.replace('/Wh','/kWh')
    elif kind=="money" and unit in {"DKK","kr","EUR"}: valid=True
    if not valid: result['status']='wrong_unit'; return result
    result.update(value=value,unit=unit,status="ok",updated_at=state.get('last_updated'))
    return result


@router.get("/api/family/energy")
def energy(user=Depends(adults)):
    settings=load_config().energy
    if not any(settings.values()): return {"status":"not_configured","metrics":[metric(k,"",None) for k in ENERGY]}
    try: data=states(); status='ok'
    except (HomeAssistantConfigurationError,HomeAssistantUnavailable): data={};status='unavailable'
    return {"status":status,"metrics":[metric(k,settings.get(k,""),data.get(settings.get(k,""))) for k in ENERGY],"checked_at":datetime.now(timezone.utc).isoformat()}


@router.get("/api/family/cameras")
def cameras(user=Depends(adults)):
    setup=load_config()
    try: data=states() if setup.cameras else {}; status='ok' if setup.cameras else 'not_configured'
    except (HomeAssistantConfigurationError,HomeAssistantUnavailable): data={}; status='unavailable'
    cameras=[]
    for i,camera in enumerate(setup.cameras):
        state=data.get(camera.entity,{})
        raw=state.get('state')
        availability='unavailable' if raw in {'unavailable','unknown',None} else 'available'
        cameras.append({"id":i,"name":camera.name,"status":availability,"state":raw if availability=='available' else None,"live_url":camera.live_url,"recordings_url":camera.recordings_url,"updated_at":state.get('last_updated')})
    try: scrypted=web_url(setup.scrypted_url or os.getenv('SCRYPTED_URL',''))
    except ValueError: scrypted=''
    return {"status":status,"cameras":cameras,"scrypted_url":scrypted}


@router.get("/api/family/cameras/{camera_id}/snapshot")
def snapshot(camera_id:int,user=Depends(adults)):
    setup=load_config()
    if not 0<=camera_id<len(setup.cameras): raise HTTPException(404,"Kameraet findes ikke")
    entity=setup.cameras[camera_id].entity
    try: connection=load_home_assistant_connection()
    except HomeAssistantConfigurationError: connection=None
    if not connection: raise HTTPException(503,"Home Assistant er ikke tilsluttet")
    signature=(config.DB_PATH,connection.base_url,connection.access_value,entity)
    with _lock: cached=_image_cache.get(signature)
    if cached and time.monotonic()-cached[0]<10: content,mime=cached[1:]
    else:
        try:
            with httpx.Client(timeout=connection.timeout_seconds,follow_redirects=False) as client:
                with client.stream('GET',f'{connection.base_url}/api/camera_proxy/{entity}',headers={'Authorization':f'Bearer {connection.access_value}'}) as response:
                    mime=response.headers.get('content-type','').split(';')[0].lower()
                    if not response.is_success or mime not in {'image/jpeg','image/png','image/webp'}: raise HTTPException(503,"Snapshot er ikke tilgængeligt")
                    chunks=[];size=0
                    for chunk in response.iter_bytes():
                        size+=len(chunk)
                        if size>5*1024*1024: raise HTTPException(503,"Snapshot er for stort")
                        chunks.append(chunk)
                    content=b''.join(chunks)
                    if not content: raise HTTPException(503,"Tomt snapshot")
        except httpx.HTTPError: raise HTTPException(503,"Kameraet svarer ikke")
        with _lock:
            if len(_image_cache)>=24: _image_cache.clear()
            _image_cache[signature]=(time.monotonic(),content,mime)
    return Response(content,media_type=mime,headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})


@router.get("/api/family/energy/history/{key}")
def energy_history(key:str,user=Depends(adults)):
    from datetime import timedelta
    if key not in ENERGY: raise HTTPException(404,"Målingen findes ikke")
    entity=load_config().energy.get(key,'')
    if not entity: return {"status":"not_configured","points":[],"unit":""}
    end=datetime.now(timezone.utc);start=end-timedelta(hours=24)
    try:
        connection=load_home_assistant_connection()
        if not connection: raise HomeAssistantUnavailable()
        current=states().get(entity,{})
        response=HomeAssistantClient(connection).get_json(f"/api/history/period/{start.isoformat()}",params={"filter_entity_id":entity,"end_time":end.isoformat()})
    except (HomeAssistantConfigurationError,HomeAssistantUnavailable):
        return {"status":"unavailable","points":[],"unit":""}
    rows=response[0] if isinstance(response,list) and response and isinstance(response[0],list) else []
    points=[];unit=''
    for row in rows:
        if not isinstance(row,dict): continue
        if row.get('entity_id',entity)!=entity: continue
        measured=metric(key,entity,{**row,'attributes':row.get('attributes') or current.get('attributes',{})})
        when=row.get('last_changed') or row.get('last_updated')
        try: timestamp=datetime.fromisoformat(str(when).replace('Z','+00:00'))
        except (ValueError,TypeError): continue
        if timestamp.tzinfo is None or timestamp>end: continue
        timestamp=max(timestamp,start)
        if measured['status']=='ok':
            if unit and measured['unit']!=unit: continue
            unit=measured['unit'];points.append({'time':timestamp.isoformat(),'value':measured['value']})
        else: points.append({'time':timestamp.isoformat(),'value':None})
    points.sort(key=lambda p:p['time'])
    # Bound payload while retaining the latest point. No fabricated points.
    if len(points)>400:
        stride=math.ceil(len(points)/399);points=points[::stride]+[points[-1]]
    return {"status":"ok" if points else "empty","points":points,"unit":unit,"label":ENERGY[key][0]}
