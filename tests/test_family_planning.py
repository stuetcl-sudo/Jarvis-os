from datetime import date, timedelta
from test_pets import client, login
from app.db import connect, init_db

BASE = '/api/family/planning'


def test_shared_week_permissions_and_csrf(client):
    assert client.get(BASE).status_code == 401
    assert 'data-family-card="planning"' not in client.get('/').text
    headers = login(client, 'adult')
    data = client.get(BASE).json()
    assert len(data['days']) == 7
    assert data['days'][0]['date'] == data['today']
    day = data['today']
    payload = {'meal': 'Lasagne', 'cook': 'Mor', 'reminders': ['Svømmetøj'], 'pickup': 'Far', 'pickup_time': '15:30'}
    assert client.put(f'{BASE}/{day}', json=payload).status_code == 403
    assert client.put(f'{BASE}/{day}', headers=headers, json=payload).status_code == 200
    init_db()
    assert client.get(BASE).json()['days'][0]['meal'] == 'Lasagne'
    assert client.get(BASE).headers['cache-control'] == 'no-store'
    child = login(client, 'child')
    assert client.get(BASE).json()['days'][0]['cook'] == 'Mor'
    assert client.get(BASE).json()['can_edit'] is False
    assert client.put(f'{BASE}/{day}', headers=child, json=payload).status_code == 403
    assert 'data-family-card="planning"' in client.get('/').text
    assert 'password' not in client.get(BASE).text
    wall = login(client, 'wall_display')
    assert client.get(BASE).status_code == 200
    assert client.put(f'{BASE}/{day}', headers=wall, json=payload).status_code == 200


def test_separate_days_and_validation(client):
    headers = login(client, 'owner')
    day = client.get(BASE).json()['today']
    tomorrow = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    assert client.put(f'{BASE}/{tomorrow}', headers=headers, json={'meal':'Tacos','ingredients':['Milk',' milk ','Tomater']}).status_code == 200
    data = client.get(BASE).json()
    assert data['days'][0]['meal'] == ''
    assert data['days'][1]['ingredients'] == ['Milk', 'Tomater']
    for payload in [{'recipe_url':'javascript:alert(1)'}, {'recipe_url':'https://user:pass@example.org'}, {'recipe_url':'https://example.org:wrong'}, {'pickup_time':'25:00'}, {'ingredients':['x'*161]}, {'reminders':['']}, {'unknown':1}]:
        assert client.put(f'{BASE}/{day}', headers=headers, json=payload).status_code == 422
    assert client.get(f'{BASE}?start=9999-12-30').status_code == 422
    assert client.get('/api/family/meal-plan?days=8').status_code == 422


def test_ingredients_atomic_dedup_and_missing_list(client):
    headers = login(client, 'adult')
    day = client.get(BASE).json()['today']
    list_id = client.post('/api/family/shopping', headers=headers, json={'name':'Ugens mad'}).json()['id']
    client.post(f'/api/family/shopping/{list_id}/items', headers=headers, json={'name':'milk'})
    client.put(f'{BASE}/{day}', headers=headers, json={'meal':'Pasta','ingredients':['Milk','Pasta','Tomater']})
    result = client.post(f'{BASE}/{day}/shopping', headers=headers, json={'list_id':list_id})
    assert result.json() == {'added':2,'already_present':1}
    assert client.post(f'{BASE}/{day}/shopping', headers=headers, json={'list_id':list_id}).json()['added'] == 0
    assert len(client.get('/api/family/shopping').json()['lists'][0]['items']) == 3
    assert client.post(f'{BASE}/{day}/shopping', headers=headers, json={'list_id':999}).status_code == 404
    with connect() as conn:
        conn.executemany('INSERT INTO shopping_items(list_id,name,quantity,category,note) VALUES (?, ?, "", "", "")', [(list_id,f'Vare {i}') for i in range(496)])
    client.put(f'{BASE}/{day}', headers=headers, json={'ingredients':['New 1','New 2']})
    assert client.post(f'{BASE}/{day}/shopping', headers=headers, json={'list_id':list_id}).status_code == 409
    assert len(client.get('/api/family/shopping').json()['lists'][0]['items']) == 499
    child = login(client, 'child')
    assert client.post(f'{BASE}/{day}/shopping', headers=child, json={'list_id':list_id}).status_code == 403
