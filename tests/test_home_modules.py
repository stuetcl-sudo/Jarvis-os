import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import httpx
import pytest
from test_pets import client, login
from app import home_modules as modules, settings_store, config
from app.home_assistant import HomeAssistantConnection, HomeAssistantUnavailable

CONFIG='/api/admin/home-modules/config'
SHOP='/api/family/shopping'


def save(client,headers,energy=None,cameras=None):
    response=client.put(CONFIG,headers=headers,json={'energy':energy or {},'cameras':cameras or []})
    assert response.status_code==200,response.text


def test_shopping_roles_csrf_and_list_isolation(client):
    assert client.get(SHOP).status_code==401
    headers=login(client,'owner')
    assert client.post(SHOP,json={'name':'Dagligvarer'}).status_code==403
    first=client.post(SHOP,headers=headers,json={'name':'Dagligvarer'}).json()['id']
    second=client.post(SHOP,headers=headers,json={'name':'Byggemarked'}).json()['id']
    item=client.post(f'{SHOP}/{first}/items',headers=headers,json={'name':'Mælk','quantity':'2 liter','category':'Mejeri','note':'Økologisk'}).json()['id']
    assert client.put(f'{SHOP}/{second}/items/{item}/state',headers=headers,json={'done':True}).status_code==404
    child=login(client,'child')
    assert client.put(f'{SHOP}/{first}/items/{item}/state',headers=child,json={'done':True}).status_code==200
    assert client.put(f'{SHOP}/{first}/items/{item}/state',headers=child,json={'done':False}).status_code==200
    assert client.post(f'{SHOP}/{first}/items',headers=child,json={'name':'Brød'}).status_code==201
    assert client.delete(f'{SHOP}/{first}',headers=child).status_code==403
    assert client.put(f'{SHOP}/{first}/items/{item}',headers=child,json={'name':'ændret'}).status_code==403
    assert client.post(f'{SHOP}/{first}/items',headers=child,json={'name':' '}).status_code==422
    data=client.get(SHOP).json()
    assert len(data['lists'][0]['items'])==2
    assert next(i for i in data['lists'][0]['items'] if i['name']=='Mælk')['quantity']=='2 liter'
    assert client.post(SHOP,headers=child,json={'name':'nej'}).status_code==403


def test_shopping_completed_and_cascade(client):
    headers=login(client,'adult')
    list_id=client.post(SHOP,headers=headers,json={'name':'Liste'}).json()['id']
    for name,done in [('Mælk',True),('Brød',False)]:
        item=client.post(f'{SHOP}/{list_id}/items',headers=headers,json={'name':name}).json()['id']
        client.put(f'{SHOP}/{list_id}/items/{item}/state',headers=headers,json={'done':done})
    assert client.delete(f'{SHOP}/{list_id}/completed',headers=headers).status_code==200
    assert [i['name'] for i in client.get(SHOP).json()['lists'][0]['items']]==['Brød']
    assert client.put(f'{SHOP}/{list_id}',headers=headers,json={'name':'Ny liste'}).status_code==200
    assert client.delete(f'{SHOP}/{list_id}',headers=headers).status_code==200
    assert client.get(SHOP).json()['lists']==[]


@pytest.mark.parametrize('role',[None,'child','wall_display'])
def test_energy_camera_privacy_and_owner_settings(client,role):
    if role: login(client,role)
    expected=403 if role else 401
    for path in ['/api/family/energy','/api/family/energy/history/solar_power','/api/family/cameras','/api/family/cameras/0/snapshot',CONFIG]:
        assert client.get(path).status_code==expected
    assert 'data-family-card="energy"' not in client.get('/').text
    assert 'data-family-card="cameras"' not in client.get('/').text


def test_owner_config_validation_and_adult_read_only(client):
    headers=login(client,'owner')
    assert client.put(CONFIG,json={}).status_code==403
    for payload in [
        {'energy':{'solar_power':'camera.x'}},
        {'energy':{'injected':'sensor.x'}},
        {'cameras':[{'name':'Test','entity':'camera.x','live_url':'javascript:alert(1)'}]},
        {'cameras':[{'name':'Test','entity':'camera.x','recordings_url':'http://user:password@camera/'}]},
        {'cameras':[{'name':'Test','entity':'camera.x'},{'name':'Duplicate','entity':'camera.x'}]},
    ]:
        assert client.put(CONFIG,headers=headers,json=payload).status_code==422
    save(client,headers,{'solar_power':'sensor.solar'})
    adult=login(client,'adult')
    assert client.get('/api/family/energy').status_code==200
    assert client.get(CONFIG).status_code==403
    assert client.put(CONFIG,headers=adult,json={}).status_code==403


def test_energy_real_units_missing_nan_and_unavailable(client):
    headers=login(client,'owner')
    save(client,headers,{'solar_power':'sensor.solar','solar_today':'sensor.day','battery':'sensor.battery','price':'sensor.price'})
    sample={
        'sensor.solar':{'state':'2500','attributes':{'unit_of_measurement':'W'}},
        'sensor.day':{'state':'18400','attributes':{'unit_of_measurement':'Wh'}},
        'sensor.battery':{'state':'nan','attributes':{'unit_of_measurement':'%'}},
        'sensor.price':{'state':'0.003','attributes':{'unit_of_measurement':'DKK/Wh'}},
    }
    with patch.object(modules,'states',return_value=sample):
        metrics={m['key']:m for m in client.get('/api/family/energy').json()['metrics']}
    assert metrics['solar_power']['value']==2.5 and metrics['solar_power']['unit']=='kW'
    assert metrics['solar_today']['value']==18.4
    assert metrics['battery']['value'] is None
    assert metrics['price']['value']==3
    assert metrics['import_today']['status']=='not_configured'
    assert modules.metric('solar_today','sensor.x',{'state':'4','attributes':{'unit_of_measurement':'W'}})['status']=='wrong_unit'
    with patch.object(modules,'states',side_effect=HomeAssistantUnavailable()):
        data=client.get('/api/family/energy').json()
    assert data['status']=='unavailable' and all(m['value'] is None for m in data['metrics'])


def test_history_filters_entity_and_handles_gaps(client):
    headers=login(client,'owner');save(client,headers,{'solar_power':'sensor.solar'})
    now=datetime.now(timezone.utc)
    rows=[{'entity_id':'sensor.solar','state':value,'last_changed':(now-timedelta(hours=h)).isoformat(),'attributes':{'unit_of_measurement':'W'}} for h,value in [(3,'1000'),(2,'unavailable'),(1,'2000')]]
    with patch.object(modules,'load_home_assistant_connection',return_value=HomeAssistantConnection('http://ha','private',5)),patch.object(modules,'states',return_value={}),patch.object(modules.HomeAssistantClient,'get_json',return_value=[rows]) as get:
        data=client.get('/api/family/energy/history/solar_power').json()
    assert [p['value'] for p in data['points']]==[1,None,2]
    assert get.call_args.kwargs['params']['filter_entity_id']=='sensor.solar'
    assert client.get('/api/family/energy/history/not-a-key').status_code==404


def test_camera_snapshot_proxy_auth_allowlist_and_redirect(client):
    headers=login(client,'owner')
    save(client,headers,cameras=[{'name':'Indkørsel','entity':'camera.drive','live_url':'https://camera.example/live'}])
    conn=HomeAssistantConnection('http://home-assistant','private-token',5)
    original=httpx.Client
    requests=[]
    def handle(request):
        requests.append(request)
        assert request.url.path=='/api/camera_proxy/camera.drive'
        assert request.headers['authorization']=='Bearer private-token'
        return httpx.Response(200,headers={'Content-Type':'image/jpeg'},content=b'\xff\xd8\xfftest')
    def factory(**kwargs): return original(transport=httpx.MockTransport(handle),**kwargs)
    with patch.object(modules,'load_home_assistant_connection',return_value=conn),patch.object(modules.httpx,'Client',side_effect=factory):
        response=client.get('/api/family/cameras/0/snapshot')
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert b'private-token' not in response.content
        assert client.get('/api/family/cameras/0/snapshot').status_code==200
        assert len(requests)==1
        assert client.get('/api/family/cameras/1/snapshot').status_code==404
    modules._image_cache.clear()
    def redirect(request): return httpx.Response(302,headers={'Location':'http://evil.invalid'})
    with patch.object(modules,'load_home_assistant_connection',return_value=conn),patch.object(modules.httpx,'Client',side_effect=lambda **kwargs: original(transport=httpx.MockTransport(redirect),**kwargs)):
        assert client.get('/api/family/cameras/0/snapshot').status_code==503


def test_camera_status_is_not_invented(client):
    headers=login(client,'owner');save(client,headers,cameras=[{'name':'Garage','entity':'camera.garage'}])
    with patch.object(modules,'states',return_value={'camera.garage':{'state':'unavailable'}}):
        data=client.get('/api/family/cameras').json()
    assert data['cameras'][0]['status']=='unavailable'
    with patch.object(modules,'states',return_value={'camera.garage':{'state':'idle'}}):
        assert client.get('/api/family/cameras').json()['cameras'][0]['status']=='available'
