"""Admin provisions managers without changing existing credentials or CRM data."""
import os,sys,tempfile,base64,json,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='fixture-admin-password-123')
 import server,crm_store,warehouse_store
 server.app.config['SESSION_COOKIE_SECURE']=False
 c=server.app.test_client()
 def basic(name,pw):return {'Authorization':'Basic '+base64.b64encode((name+':'+pw).encode()).decode(),'X-Requested-With':'OSK-Map'}
 admin=basic('admin',os.environ['APP_PASSWORD']);endpoint='/api/admin/users'
 body={'login':'Тест Новый','password':'testpw08'}
 assert c.post(endpoint,json=body).status_code==401
 assert c.post(endpoint,headers={k:v for k,v in admin.items() if k!='X-Requested-With'},json=body).status_code==403
 assert c.post(endpoint,headers=admin|{'Origin':'https://other.invalid'},json=body).status_code==403
 assert c.post(endpoint,headers=admin,json=body|{'login':'admin'}).status_code==409
 assert c.post(endpoint,headers=admin,json=body|{'role':'admin'}).status_code==400
 warehouse_store.provision({'login':'Тест Склад','password':'stockpw08'})
 assert c.post(endpoint,headers=admin,json=body|{'login':'Тест Склад'}).status_code==409
 assert c.post(endpoint,headers=admin,json=body).status_code==201
 user=basic(body['login'],body['password']);me=c.get('/api/me',headers=user).json
 assert me['role']=='manager' and me['canExport'] is False and me['manager']==body['login']
 assert c.post(endpoint,headers=admin,json=body|{'password':'changed-password'}).json['created'] is False
 assert c.get('/api/me',headers=basic(body['login'],'changed-password')).status_code==401
 assert c.get('/api/me',headers=user).status_code==200
 for auth in [user,basic('Тест Склад','stockpw08')]:assert c.post(endpoint,headers=auth,json=body|{'login':'Another Person'}).status_code==403
 text=c.get('/login').get_data(as_text=True);assert text.count('value="Тест Новый"')==1
 csrf=re.search('name="csrf" value="([^"]+)"',text)[1]
 assert c.post('/login',data={'login':body['login'],'password':body['password'],'csrf':csrf}).status_code==303
 assert c.get('/api/me').json['role']=='manager'
 for path in ['/','/companies/','/requests/','/warehouse/','/warehouse/api/prices','/api/records']:assert c.get(path).status_code==200,path
 assert c.get('/warehouse/api/prices.xlsx').status_code==404 # allowed but no catalogue loaded
 for path in ['/warehouse/api/admin/stock.xlsx','/offices.csv']:assert c.get(path).status_code==403,path
 assert c.post('/api/export/table/xlsx',headers={'X-Requested-With':'OSK-Map'},json={}).status_code==403
 assert c.get('/api/me',headers=admin).json['role']=='manager' # existing session remains authoritative
 with crm_store.connect() as db:assert db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]==1
 print('PASS users: administrator-only create; supplied password; all-section manager role; full exports denied; new dropdown entry; existing passwords and warehouse accounts preserved; CSRF')
