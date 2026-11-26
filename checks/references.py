"""Admin-only reference library: access, deep links and crosswalk data integrity."""
import os,sys,tempfile,json,re,base64
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='reference-fixture-password')
 import server
 server.app.config['SESSION_COOKIE_SECURE']=False
 client=server.app.test_client()
 def auth(login,pw):return {'Authorization':'Basic '+base64.b64encode((login+':'+pw).encode()).decode(),'X-Requested-With':'OSK-Map'}
 admin=auth('admin',os.environ['APP_PASSWORD'])
 for role in ['manager','warehouse']:
  assert client.post('/api/admin/accounts',headers=admin,json={'login':'Reference '+role,'password':'reference-fixture-password','role':role}).status_code==201
 paths=['/references','/references/','/references/index.html','/references/cables.json','/references/references.js','/references/references.css','/companies/references/index.html','/companies/references/cables.json']
 for path in paths:
  assert client.get(path).status_code==(302 if path in ['/references','/references/'] else 401),path
  for role in ['manager','warehouse']:
   for method in ['get','head']:assert getattr(client,method)(path,headers=auth('Reference '+role,'reference-fixture-password')).status_code==403,(path,role,method)
  response=client.get(path,headers=admin);assert response.status_code==(302 if path=='/references' else 200),(path,response.status_code)
  assert 'no-store' in response.headers['Cache-Control'],path
 data=client.get('/references/cables.json',headers=admin).json
 makers={m['id']:m for m in data['manufacturers']};groups={g['id']:g for g in data['groups']}
 assert len(makers)==len(data['manufacturers'])>=24 and {m['country'] for m in makers.values()}=={'Россия','Беларусь'}
 assert len(data['entries'])>=150 and len({e['id'] for e in data['entries']})==len(data['entries'])
 assert all(e['manufacturer'] in makers and e['group'] in groups and e['source'] in data['sources'] and e['mark'].strip() for e in data['entries'])
 assert all(e['kind'] in ['crosswalk','catalog'] for e in data['entries'])
 assert set(makers)=={e['manufacturer'] for e in data['entries']}
 assert makers['integra']['country']=='Беларусь' and 'СОЮЗ-КАБЕЛЬ' in makers['integra']['aliases']
 assert len([m for m in makers.values() if 'СОЮЗ-КАБЕЛЬ' in m['name']])==1
 assert all(g['construction'] and g['differences'] for g in groups.values())
 assert all(urlsplit(s['url']).scheme=='https' for s in data['sources'].values())
 assert data['coverage'] and data['coverageNotes'] and len(data['comparisonFields'])>=10
 assert next(e for e in data['entries'] if e['manufacturer']=='starlink' and e['mark']=='СЛ-ОКПЦ-Д2')['group']=='drop-round'
 assert next(e for e in data['entries'] if e['manufacturer']=='minsk' and e['mark']=='КСО-ВСЦЗПКс')['group']=='eight-central'
 text=client.get('/login?next=/references/').get_data(as_text=True);csrf=re.search('name="csrf" value="([^\"]+)"',text)[1]
 response=client.post('/login',data={'next':'/references/','login':'admin','password':os.environ['APP_PASSWORD'],'csrf':csrf})
 assert response.status_code==303 and response.location=='/references/'
 assert 'references-card' in client.get('/portal-home.js').get_data(as_text=True)
print('PASS: admin-only documents/data/aliases GET+HEAD; no-store; safe login return; RU/BY crosswalk integrity; aliases and construction distinctions')
