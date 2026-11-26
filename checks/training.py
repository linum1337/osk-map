"""Training is owner-only, including raw assets and company aliases."""
import os,sys,tempfile,base64,json,re
from urllib.parse import urlsplit
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='training-fixture-password')
 import server,admin_store
 client=server.app.test_client();server.app.config['SESSION_COOKIE_SECURE']=False
 def basic(name,password):return {'Authorization':'Basic '+base64.b64encode((name+':'+password).encode()).decode(),'X-Requested-With':'OSK-Map'}
 admin=basic('admin',os.environ['APP_PASSWORD'])
 for role in ('manager','warehouse'):
  response=client.post('/api/admin/accounts',headers=admin,json={'login':'Training '+role,'password':'training-fixture-pw','role':role});assert response.status_code==201,response.json
 paths=['/training/courses.json','/training/assets/signal-path.svg','/training/assets/cable-and-fibres.svg','/companies/training/assets/signal-path.svg','/training','/training/','/training/index.html','/training/optical-cable/','/training/optical-cable/index.html','/training/optical-cable/course.json','/training/training.js','/training/training.css','/companies/training/index.html','/companies/training/optical-cable/course.json','/companies/training/training.js','/companies/training/training.css']
 for path in paths:
  assert client.get(path).status_code==(302 if path in server.PORTAL_PAGES else 401),path
  for role in ('manager','warehouse'):
   auth=basic('Training '+role,'training-fixture-pw')
   for method in ('get','head'):
    assert getattr(client,method)(path,headers=auth).status_code==403,(role,path,method)
  response=client.get(path,headers=admin);assert response.status_code==(302 if path=='/training' else 200),(path,response.status_code)
  assert 'no-store' in response.headers['Cache-Control'],path
 assert client.get('/training/',headers={'Accept':'text/html'}).status_code==302
 data=client.get('/training/optical-cable/course.json',headers=admin).json
 assert len(data['lessons'])==18 and len(data['quiz'])==24
 assert len({x['id'] for x in data['lessons']})==18
 assert data['audience']=='Продажи в России'
 allowed_sources={'ocs01.ru','incab.ru','incab-holding.ru','mk-f.ru','spkb.ru','vols.expert','www.expert-labs.ru','cdn.nag.ru'}
 assert all(urlsplit(source[1]).hostname in allowed_sources for source in data['sources'].values())
 assert set(data['sources'])=={ref for lesson in data['lessons'] for ref in lesson['sources']}
 for question in data['quiz']:
  assert 0<=question['answer']<len(question['options']) and question['explanation']
  assert any(l['id']==question['lesson'] for l in data['lessons'])
 assert len(data['cases'])==4 and data['memos']
 for case in data['cases']:
  assert case['task'] and case['answer'] and case['criteria']
  assert all(any(l['id']==id for l in data['lessons']) for id in case['lessons'])
 for lesson in data['lessons']:
  assert lesson['blocks'] and lesson['goal'] and lesson['module']
  assert lesson['practice']['task'] and lesson['practice']['answer'] and lesson['practice']['criteria']
  for ref in lesson['sources']:assert ref in data['sources']
 # Every listed product course must work independently and retain owner-only access.
 catalog=client.get('/training/courses.json',headers=admin).json
 assert {c['slug'] for c in catalog}==set(server.TRAINING_COURSES)
 assert len(catalog)==5
 for item in catalog:
  slug=item['slug'];base='/training/'+slug+'/'
  assert base in server.PORTAL_PAGES and base.rstrip('/') in server.PORTAL_PAGES
  page=client.get(base,headers=admin)
  assert page.status_code==200 and ('data-course="'+base+'course.json"') in page.get_data(as_text=True)
  assert client.get(base.rstrip('/'),headers=admin).status_code==308
  course=client.get(base+'course.json',headers=admin).json
  assert course['title']==item['title'] or (slug=='optical-cable' and course['title']=='Продажи оптического кабеля')
  assert len(course['lessons'])==item['lessons'] and len(course['quiz'])==item['questions'] and len(course['cases'])==item['cases']
  ids={l['id'] for l in course['lessons']}
  assert len(ids)==len(course['lessons'])
  assert set(course['sources'])=={ref for l in course['lessons'] for ref in l['sources']}
  assert all(urlsplit(v[1]).scheme=='https' and urlsplit(v[1]).hostname in allowed_sources|{'ssd.ru','lanmaster.ru','install-ltd.ru','www.install-ltd.ru','shop.nag.ru','b2b.nag.ru'} for v in course['sources'].values())
  assert course['memos'] and course['glossary'] and course['audience']=='Продажи в России'
  for l in course['lessons']:
   assert l['blocks'] and l['goal'] and l['module']
   if slug!='optical-cable':assert len(l['blocks'])>=3 and l['sources']
   assert l['practice']['task'] and l['practice']['answer'] and l['practice']['criteria']
  for q in course['quiz']:
   assert q['lesson'] in ids and q['explanation'] and 0<=q['answer']<len(q['options'])
  for c in course['cases']:
   assert c['task'] and c['answer'] and c['criteria'] and set(c['lessons'])<=ids
  for path in [base,base+'index.html',base+'course.json','/companies'+base+'course.json']:
   assert client.get(path).status_code==(302 if path==base else 401),path
   for role in ('manager','warehouse'):
    for method in ('get','head'):
     assert getattr(client,method)(path,headers=basic('Training '+role,'training-fixture-pw')).status_code==403,(path,role)
   assert 'no-store' in client.get(path,headers=admin).headers['Cache-Control']
 # New course deep links must survive session login, including the selected lesson.
 for slug in server.TRAINING_COURSES:
  login_client=server.app.test_client();target='/training/'+slug+'/#'+('purpose' if slug!='optical-cable' else 'basics')
  text=login_client.get('/login',query_string={'next':target}).get_data(as_text=True)
  csrf=re.search('name="csrf" value="([^"]+)"',text)[1]
  response=login_client.post('/login',data={'next':target,'login':'admin','password':os.environ['APP_PASSWORD'],'csrf':csrf})
  assert response.status_code==303 and response.location==target,(slug,response.location)
 assert client.get('/training/not-a-course/',headers=admin).status_code==404
 # Session login can return to the actual course, and existing areas remain accessible.
 text=client.get('/login?next=/training/optical-cable/').get_data(as_text=True)
 csrf=re.search('name="csrf" value="([^"]+)"',text)[1]
 response=client.post('/login?next=/training/optical-cable/',data={'login':'admin','password':os.environ['APP_PASSWORD'],'csrf':csrf})
 assert response.status_code==303 and response.location=='/training/optical-cable/'
 assert client.get('/training/optical-cable/').status_code==200
 for path in ['/','/companies/','/warehouse/','/admin/']:assert client.get(path).status_code==200,path
print('PASS: owner-only training documents/assets/aliases GET+HEAD; anonymous login; no-store; five independent courses; complete content; deep-link login; existing sections')
