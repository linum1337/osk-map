"""Warehouse access boundaries, balances, concurrent writes and full audit."""
import base64
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as temp:
 os.environ.update(DATA_DIR=temp,APP_USER='admin',APP_PASSWORD='warehouse-test-admin-12345')
 import server,crm_store,manage_users,warehouse_store as w
 server.app.config['SESSION_COOKIE_SECURE']=False
 manage_users.import_users([{'login':'Тест Менеджер','manager':crm_store.MANAGERS[0],'password':'existing-manager-password-123'}])
 original={'officeId':'office-1','name':'Client fixture','notes':'Saved note','status':'В работе','manager':crm_store.MANAGERS[0],'bitrixData':{'Название':'Original CRM'},'crmMatches':[{'id':'fixture'}]}
 with crm_store.connect() as db:
  db.execute('INSERT INTO records VALUES(?,?,1)',('office-1',json.dumps(original)))
  accounts_before=db.execute('SELECT * FROM accounts ORDER BY login').fetchall()
 def basic(login,password):return {'Authorization':'Basic '+base64.b64encode((login+':'+password).encode()).decode(),'X-Requested-With':'OSK-Map'}
 admin=basic('admin',os.environ['APP_PASSWORD']);manager=basic('Тест Менеджер','existing-manager-password-123')
 c=server.app.test_client()
 assert c.get('/warehouse/api/items').status_code==401
 assert c.post('/warehouse/api/admin/users',headers=manager,json={'login':'Test Person','password':'new-password'}).status_code==403
 # Provisioning a warehouse-only identity must never reset any existing account.
 assert c.post('/warehouse/api/admin/users',headers=admin,json={'login':'admin','password':'changed-password'}).status_code==409
 assert c.post('/warehouse/api/admin/users',headers=admin,json={'login':'Тест Менеджер','password':'changed-password'}).status_code==409
 user_body={'login':'Тест Склад','password':'warehouse-only-fixture-password'}
 assert c.post('/warehouse/api/admin/users',headers=admin,json=user_body).status_code==201
 assert c.post('/warehouse/api/admin/users',headers=admin,json={**user_body,'password':'different-password'}).json['created'] is False
 assert c.get('/api/me',headers=basic(user_body['login'],'different-password')).status_code==401
 stock_user=basic(user_body['login'],user_body['password'])
 assert c.get('/api/me',headers=stock_user).json['role']=='warehouse'
 assert c.post('/warehouse/api/items/missing/action',headers=stock_user,json={'action':[],'version':1,'requestKey':'invalid-action-0001'}).status_code==400
 page=c.get('/login').get_data(as_text=True)
 assert 'Тест Склад' in page and '/warehouse/login' not in page
 def signin(client,name,password,next_page='/'):
  import re
  text=client.get('/login').get_data(as_text=True);token=re.search('name="csrf" value="([^"]+)"',text)[1]
  return client.post('/login',data={'login':name,'password':password,'csrf':token,'next':next_page})
 session_client=server.app.test_client()
 login=signin(session_client,user_body['login'],user_body['password'],'/companies/')
 assert login.status_code==303 and login.location=='/warehouse/'
 assert session_client.get('/warehouse/').status_code==200
 assert session_client.get('/',headers={'Accept':'text/html'}).location=='/warehouse/'
 assert session_client.get('/api/me').json['role']=='warehouse'
 for path in ['/api/records','/api/head-office-requests','/companies/data.js','/data.js','/scope-data.js','/suppliers/suppliers.json','/suppliers/data.js','/transport/','/requests/','/api/export/table/xlsx','/warehouse/api/admin/users','/warehouse/api/admin/import']:
  method=session_client.post if '/admin/' in path or '/export/' in path else session_client.get
  assert method(path,headers={'X-Requested-With':'OSK-Map'}).status_code==403,path
 assert c.get('/api/me',headers=manager).json['role']=='manager'
 assert c.get('/api/records',headers=manager).status_code==200

 def item(row,reel,length,rod='1,2 ROD'):
  return {'sourceRow':row,'pallet':'1','reel':reel,'length':length,'sourceLength':length,'sourceUnit':'м','construction':'Fixture cable','marking':'Fixture marking','rod':rod,'note':'Original note','location':'Fixture storage'}
 payload={'format':'osk-krasnodar-stock-v1','source':'fixture.xlsx','sourceDigest':'a'*64,'sourceData':{'headers':['original header']},'items':[item(2,'1',100),item(3,'2',200,'1.2 ROD'),item(4,'3',50,'1.0 EAA')]}
 invalid=copy.deepcopy(payload);invalid['items'][1]['length']=-1
 assert c.post('/warehouse/api/admin/import',headers=admin,json=invalid).status_code==400
 assert w.snapshot()['totals']['items']==0
 assert c.post('/warehouse/api/admin/import',headers=admin,json=payload).status_code==201
 assert c.post('/warehouse/api/admin/import',headers=admin,json=payload).json['imported'] is False
 assert c.post('/warehouse/api/admin/import',headers=admin,json={**payload,'sourceDigest':'b'*64}).status_code==409
 snap=w.snapshot();assert len(snap['groups'])==2 and snap['totals']['available']==350
 first=snap['items'][0];id=first['id'];clock=1000000;w.now_ms=lambda:clock
 def action(action,version,key,comment='',auth=stock_user,item_id=id):
  return c.post('/warehouse/api/items/'+item_id+'/action',headers=auth,json={'action':action,'version':version,'requestKey':key,'comment':comment,'actor':'FAKE','role':'admin'})
 assert c.post('/warehouse/api/items/'+id+'/action',headers={k:v for k,v in stock_user.items() if k!='X-Requested-With'},json={}).status_code==403
 assert c.post('/warehouse/api/items/'+id+'/action',headers={**stock_user,'Origin':'https://other.invalid'},json={}).status_code==403
 reserved=action('reserve',1,'reserve-request-0001','For customer fixture')
 assert reserved.status_code==200 and reserved.json['item']['updatedBy']==user_body['login']
 assert reserved.json['stock']['totals']['available']==250 and reserved.json['stock']['totals']['reserved']==100
 assert action('reserve',1,'reserve-request-0002',auth=manager).status_code==409
 assert action('reserve',1,'reserve-request-0001').json['repeated'] is True
 assert action('reserve',1,'reserve-request-0001',auth=manager).status_code==409
 sold=action('sell',2,'sale-request-0000001',auth=manager)
 assert sold.status_code==200 and sold.json['item']['soldBy']=='Тест Менеджер'
 assert sold.json['stock']['totals']['reserved']==0 and sold.json['stock']['totals']['sold']==100
 assert sold.json['stock']['totals']['available']==250
 clock+=9999
 assert id in {r['id'] for r in w.snapshot()['items']}
 clock+=1
 assert id not in {r['id'] for r in w.snapshot()['items']}
 assert id in {r['id'] for r in w.snapshot(True)['items']}
 assert id not in {r['id'] for r in c.get('/warehouse/api/items',headers=stock_user).json['items']}
 assert id in {r['id'] for r in c.get('/warehouse/api/items?show_sold=1',headers=stock_user).json['items']}
 audit=c.get('/warehouse/api/history?item='+id,headers=stock_user).json
 assert [h['action'] for h in audit]==['sell','reserve','import']
 assert audit[0]['actor']=='Тест Менеджер' and audit[1]['actor']==user_body['login']
 assert audit[1]['comment']=='For customer fixture'
 assert action('restore',3,'restore-request-0001').status_code==400
 restored=action('restore',3,'restore-request-0002','Cancelled sale')
 assert restored.status_code==200 and restored.json['stock']['totals']['available']==350
 # A failed audit insert rolls back the inventory update too.
 with crm_store.connect() as db:
  prior=db.execute('SELECT * FROM warehouse_items WHERE id=?',(id,)).fetchone()
  db.execute("CREATE TRIGGER fail_warehouse BEFORE INSERT ON warehouse_history BEGIN SELECT RAISE(ABORT,'fixture'); END")
 try:w.change(id,{'action':'reserve','version':4,'requestKey':'rollback-request-0001'},{'login':'fixture','role':'warehouse'})
 except sqlite3.IntegrityError:pass
 else:raise AssertionError('Expected failure')
 with crm_store.connect() as db:
  assert db.execute('SELECT * FROM warehouse_items WHERE id=?',(id,)).fetchone()==prior
  db.execute('DROP TRIGGER fail_warehouse')
 # Two simultaneous reserves cannot consume the same reel twice.
 def reserve_once(n):return w.change(id,{'action':'reserve','version':4,'requestKey':'parallel-request-'+str(n)},{'login':'fixture-'+str(n),'role':'warehouse'})[0]
 with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(reserve_once,[1,2]))==[200,409]
 with crm_store.connect() as db:
  assert db.execute('SELECT * FROM accounts ORDER BY login').fetchall()==accounts_before
  assert json.loads(db.execute('SELECT data FROM records WHERE id="office-1"').fetchone()[0])==original
 assert session_client.post('/logout',headers={'X-Requested-With':'OSK-Map'}).status_code==200
 assert session_client.get('/warehouse/api/items').status_code==401
 print('PASS: unified login; warehouse-only route/API restrictions; existing credentials and CRM preserved; import idempotency; grouped/free/reserved/sold reconciliation; 10-second hide and show sold; server authorship; full history; CSRF; atomic rollback; concurrent reserve conflict')
