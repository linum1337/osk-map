"""Section grants are enforced on documents, APIs and aliases, with revocation."""
import os,sys,tempfile,base64,json,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='section-policy-test-password')
 import server,section_access,admin_store
 server.app.config['SESSION_COOKIE_SECURE']=False
 c=server.app.test_client()
 def headers(name='admin'):
  return {'Authorization':'Basic '+base64.b64encode((name+':section-policy-test-password').encode()).decode(),'X-Requested-With':'OSK-Map'}
 for role in ['manager','warehouse']:
  assert c.post('/api/admin/accounts',headers=headers(),json={'login':'Section '+role,'password':os.environ['APP_PASSWORD'],'role':role}).status_code==201
 def update(name,p):
  user=next(u for u in c.get('/api/admin/accounts',headers=headers()).json if u['login']==name)
  return c.post('/api/admin/accounts/change',headers=headers(),json={'login':name,'version':user['version'],'action':'permissions','permissions':p})
 p=section_access.defaults('manager');p.update(companies=False,references=False,warehouse=False,training=True)
 assert update('Section manager',p).status_code==200
 for path in ['/companies/','/companies/data.js','/data.js','/api/records','/references/','/references/cables.json','/companies/references/cables.json','/warehouse/api/items']:
  for method in ['get','head']:assert getattr(c,method)(path,headers=headers('Section manager')).status_code==403,path
 for path in ['/training/','/training/optical-cable/','/companies/training/index.html']:
  assert c.get(path,headers=headers('Section manager')).status_code==200,path
 assert c.get('/api/admin/accounts',headers=headers('Section manager')).status_code==403
 p.update(references=True,referenceCable=False,referenceClosures=True)
 assert update('Section manager',p).status_code==200
 assert c.get('/references/',headers=headers('Section manager')).status_code==200
 for path in ['/references/cables.json','/references/references.js','/references/images/ultra-0.webp','/companies/references/cables.json']:
  assert c.get(path,headers=headers('Section manager')).status_code==403,path
 for path in ['/references/closures/closures.json','/companies/references/closures/closures.json']:
  assert c.get(path,headers=headers('Section manager')).status_code==200,path
 p=section_access.defaults('warehouse');p.update(references=True,referenceCable=True)
 assert update('Section warehouse',p).status_code==200
 assert c.get('/references/cables.json',headers=headers('Section warehouse')).status_code==200
 assert c.get('/warehouse/api/prices',headers=headers('Section warehouse')).status_code==403
 assert c.get('/references/closures/closures.json',headers=headers('Section warehouse')).status_code==403
 # Existing sessions lose validity after a grant change, not only the menu.
 session_client=server.app.test_client();page=session_client.get('/login').text;token=re.search('name="csrf" value="([^"]+)"',page)[1]
 assert session_client.post('/login',data={'login':'Section manager','password':os.environ['APP_PASSWORD'],'csrf':token}).status_code==303
 assert session_client.get('/api/me').status_code==200
 assert update('Section manager',section_access.defaults('manager')).status_code==200
 assert session_client.get('/api/me').status_code==401
 stale=next(u for u in c.get('/api/admin/accounts',headers=headers()).json if u['login']=='Section manager')
 assert update('Section manager',section_access.defaults('manager')).status_code==200
 assert c.post('/api/admin/accounts/change',headers=headers(),json={'login':'Section manager','action':'permissions','version':stale['version'],'permissions':p}).status_code==409
 assert c.post('/api/admin/accounts/change',headers=headers(),json={'login':'admin','action':'permissions','version':'','permissions':section_access.defaults('warehouse')}).status_code==403
 bad=section_access.defaults('manager');bad['unknown']=True
 assert update('Section manager',bad).status_code==400
 audit=c.get('/api/admin/audit',headers=headers()).json;assert any(r['action']=='user_permissions' for r in audit)
 print('PASS: per-user section grants, API/assets/alias denials, training grant, closure/cable separation, warehouse price isolation, session revocation, stale updates, protected owner and audit')
