"""Admin-only reference library: access, deep links and crosswalk data integrity."""
import os,sys,tempfile,json,re,base64,mimetypes
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='reference-fixture-password')
 mimetypes.init()
 mimetypes.types_map.pop(".webp",None)
 mimetypes.common_types.pop(".webp",None)
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
 assert next(e for e in data['entries'] if e['manufacturer']=='starlink' and e['mark']=='СЛ-ОКПЦ-Д2')['group']=='drop-flat-tube'
 assert next(e for e in data['entries'] if e['manufacturer']=='minsk' and e['mark']=='КСО-ВСЦЗПКс')['group']=='eight-central'
 # Concrete regressions: direct constructions must connect the three manufacturers.
 assert len(data['entries'])>=550 and len(data['groups'])>=45
 for example in data['examples']:
  es=[next(e for e in data['entries'] if e['id']==id) for id in example['entries']]
  assert {e['manufacturer'] for e in es}=={'incab','starlink','kes'}
  assert {e['group'] for e in es}=={example['group']}
  assert all(e['kind']=='catalog' and e['attributes']['module'] for e in es)
 assert any(e['manufacturer']=='incab' and e['mark']=='ОВК-Б' and e['group']=='micro-wire' for e in data['entries'])
 assert any(e['manufacturer']=='incab' and e['mark']=='ОВК-Г' and e['group']=='micro-rope' for e in data['entries'])
 assert any(e['manufacturer']=='starlink' and e['mark']=='СЛ-ОКПЦ-Д2к' and e['group']=='drop-round' for e in data['entries'])
 assert not any(e['manufacturer']=='incab' and e['group']=='tape-central' and 'ТОС' in e['mark'] for e in data['entries'])
 assert all(any(e['manufacturer']=='incab' and e['group']==group for e in data['entries']) for group in ['wire-heavy','dielectric-ground','eight-dielectric','subsea','opgw-central','riser-micro','distribution-buffer','hybrid'])
 assert len(data['audit']['manufacturers'])==len(makers)
 for row in data['audit']['manufacturers']:
  assert row['records']==sum(e['manufacturer']==row['manufacturer'] for e in data['entries'])
  assert row['groups']==len({e['group'] for e in data['entries'] if e['manufacturer']==row['manufacturer']})
 # Manufacturer imagery stays behind the same access rules and has explicit provenance.
 assert client.get('/references/images/ultra-0.webp',headers=admin).content_type=='image/webp'
 assert len(data['images'])>=53
 assert makers['ultra']['country']=='Россия'
 ultra=[e for e in data['entries'] if e['manufacturer']=='ultra']
 assert {e['mark'] for e in ultra}=={'ОКПД','ОКПДп','ОКБм','ОКБц','ОКС'}
 assert all(e.get('images') for e in ultra)
 assert next(e for e in ultra if e['mark']=='ОКПДп')['group']=='drop-flat-tube'
 assert next(e for e in ultra if e['mark']=='ОКБц')['group']=='wire-central'
 for im in data['images'].values():
  assert im['src'].startswith('/references/images/') and '..' not in im['src']
  host=lambda url:(urlsplit(url).hostname or '').removeprefix('www.')
  assert host(im['sourcePage'])==host(makers[im['manufacturer']]['site'])
  allowed={host(im['sourcePage'])}
  if im['manufacturer']=='minsk':allowed.update({'static.tildacdn.com','thb.tildacdn.com'})
  assert host(im['original']) in allowed,(im['manufacturer'],im['original'])
  response=client.get(im['src'],headers=admin)
  assert response.status_code==200 and response.content_type.startswith('image/')
 assert len({im['manufacturer'] for im in data['images'].values()})>=21
 assert sum(bool(e.get('descriptionLinks')) for e in data['entries'])>=440
 assert sum(bool(e.get('images')) for e in data['entries'])>=380
 for e in data['entries']:
  assert all(data['images'][i]['manufacturer']==e['manufacturer'] for i in e.get('images',[]))
  urls=[]
  for item in e.get('descriptionLinks',[]):
   assert urlsplit(item['url']).scheme in ['http','https'] and item['label']
   assert host(item['url'])==host(makers[e['manufacturer']]['site'])
   assert item['url'] not in urls
   urls.append(item['url'])
 first=next(iter(data['images'].values()))['src']
 for path in [first,'/companies'+first]:
  assert client.get(path).status_code==401
  for role in ['manager','warehouse']:
   for method in ['get','head']:assert getattr(client,method)(path,headers=auth('Reference '+role,'reference-fixture-password')).status_code==403
  assert client.get(path,headers=admin).status_code==200
 text=client.get('/login?next=/references/').get_data(as_text=True);csrf=re.search('name="csrf" value="([^\"]+)"',text)[1]
 response=client.post('/login',data={'next':'/references/','login':'admin','password':os.environ['APP_PASSWORD'],'csrf':csrf})
 assert response.status_code==303 and response.location=='/references/'
 assert 'references-card' in client.get('/portal-home.js').get_data(as_text=True)
print('PASS: admin-only documents/data/aliases GET+HEAD; no-store; safe login return; RU/BY crosswalk integrity; aliases and construction distinctions')
