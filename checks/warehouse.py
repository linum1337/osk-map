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
 for path in ['/','/index.html']:
  for headers in [{},{'Accept':'*/*'},{'Accept':'application/json'}]:
   response=session_client.get(path,headers=headers)
   assert response.status_code==302 and response.location=='/warehouse/'
 for headers in [{'Sec-Fetch-Mode':'navigate','Accept':'*/*'},{'Sec-Fetch-Dest':'document','Accept':'application/signed-exchange;v=b3'}]:
  response=session_client.get('/companies/',headers=headers)
  assert response.status_code==302 and response.location=='/warehouse/'
 for path in ['/api/records','/warehouse/api/prices']:
  response=session_client.get(path,headers={'Sec-Fetch-Mode':'navigate','Accept':'text/html'})
  assert response.status_code==403 and response.is_json

 for path in ['/api/records','/api/head-office-requests','/companies/data.js','/data.js','/scope-data.js','/suppliers/suppliers.json','/suppliers/data.js','/transport/','/requests/','/api/export/table/xlsx','/warehouse/api/admin/users','/warehouse/api/admin/import']:
  method=session_client.post if '/admin/' in path or '/export/' in path else session_client.get
  assert method(path,headers={'X-Requested-With':'OSK-Map'}).status_code==403,path
 assert c.get('/api/me',headers=manager).json['role']=='manager'
 assert c.get('/api/records',headers=manager).status_code==200

 def item(row,reel,length,rod='1,2 ROD'):
  return {'sourceRow':row,'pallet':'1','reel':reel,'length':length,'sourceLength':length,'sourceUnit':'м','construction':'ОКПД-4А-(1,5)-1/4,8','marking':'Fixture marking','rod':rod,'note':'Original note','location':'Fixture storage'}
 payload={'format':'osk-krasnodar-stock-v1','source':'fixture.xlsx','sourceDigest':'a'*64,'sourceData':{'headers':['original header']},'items':[item(2,'1',100),item(3,'2',200,'1.2 ROD'),item(4,'3',50,'1.0 EAA')]}
 invalid=copy.deepcopy(payload);invalid['items'][1]['length']=-1
 assert c.post('/warehouse/api/admin/import',headers=admin,json=invalid).status_code==400
 assert w.snapshot()['totals']['items']==0
 assert c.post('/warehouse/api/admin/import',headers=admin,json=payload).status_code==201
 assert c.post('/warehouse/api/admin/import',headers=admin,json=payload).json['imported'] is False
 assert c.post('/warehouse/api/admin/import',headers=admin,json={**payload,'sourceDigest':'b'*64}).status_code==409
 snap=w.snapshot();assert len(snap['groups'])==2 and snap['totals']['available']==350
 first=snap['items'][0];id=first['id'];clock=1000000;w.now_ms=lambda:clock
 def action(action,version,key,comment='',auth=stock_user,item_id=id,**extra):
  return c.post('/warehouse/api/items/'+item_id+'/action',headers=auth,json={'action':action,'version':version,'requestKey':key,'comment':comment,'actor':'FAKE','role':'admin',**extra})
 assert c.post('/warehouse/api/items/'+id+'/action',headers={k:v for k,v in stock_user.items() if k!='X-Requested-With'},json={}).status_code==403
 assert c.post('/warehouse/api/items/'+id+'/action',headers={**stock_user,'Origin':'https://other.invalid'},json={}).status_code==403
 reserved=action('reserve',1,'reserve-request-0001','For customer fixture')
 assert reserved.status_code==200 and reserved.json['item']['updatedBy']==user_body['login']
 assert reserved.json['stock']['totals']['available']==250 and reserved.json['stock']['totals']['reserved']==100
 assert action('reserve',1,'reserve-request-0002',auth=manager).status_code==409
 assert action('reserve',1,'reserve-request-0001').json['repeated'] is True
 assert action('reserve',1,'reserve-request-0001',auth=manager).status_code==409
 assert action('sell',2,'sale-missing-order-01',auth=manager).status_code==400
 assert action('sell',2,'sale-blank-order-0001',orderNumber='   ').status_code==400
 sold=action('sell',2,'sale-request-0000001',auth=manager,orderNumber='ORDER-42')
 assert sold.json['item']['orderNumber']=='ORDER-42'
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
 assert audit[0]['orderNumber']=='ORDER-42'
 assert audit[1]['comment']=='For customer fixture'
 assert action('restore',3,'restore-request-0001').status_code==400
 assert action('restore',3,'unconfirmed-return-01','Cancelled sale').status_code==400
 restored=action('restore',3,'restore-request-0002','Cancelled sale',confirmed=True)
 assert 'orderNumber' not in restored.json['item']
 assert w.history(id)[0]['orderNumber']=='ORDER-42'
 assert restored.status_code==200 and restored.json['stock']['totals']['available']==350
 # Prices use an independent catalogue; Valeria/warehouse role never receives them.
 import warehouse_prices as prices
 prices.init();prices.init()
 price_payload={'format':'osk-warehouse-prices-v1','source':'fixture-prices.xlsx','sourceDigest':'c'*64,'title':'Fixture VAT price list','rows':[{'sourceRow':7,'construction':'ОКПД-4А-(1,5)-1/4,8','rod':'1.2 ROD','category':'Fixture category','cableDiameter':'4.2','weight':'15','type':'round','pricePerKm':'12345.67'}]}
 assert c.post('/warehouse/api/admin/prices',headers=stock_user,json=price_payload).status_code==403
 assert c.post('/warehouse/api/admin/prices',headers=manager,json=price_payload).status_code==403
 assert c.get('/warehouse/api/prices',headers=stock_user).status_code==403
 assert c.get('/warehouse/api/prices.xlsx',headers=stock_user).status_code==403
 assert c.get('/warehouse/api/prices.xlsx').status_code==401
 assert c.get('/warehouse/api/admin/stock.xlsx').status_code==401
 for auth in [manager,stock_user]:assert c.get('/warehouse/api/admin/stock.xlsx',headers=auth).status_code==403
 assert c.get('/warehouse/api/prices.xlsx',headers=admin).status_code==404
 assert c.post('/warehouse/api/admin/prices',headers=admin,json=price_payload).status_code==201
 assert c.post('/warehouse/api/admin/prices',headers=admin,json=price_payload).json['imported'] is False
 import io,zipfile,xml.etree.ElementTree as E
 assert c.get('/warehouse/api/prices.xlsx',headers=manager).status_code==200
 exported=c.get('/warehouse/api/prices.xlsx',headers=admin)
 assert exported.status_code==200 and 'attachment' in exported.headers['Content-Disposition']
 assert exported.mimetype=='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
 with zipfile.ZipFile(io.BytesIO(exported.data)) as z:
  ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
  sheet=E.fromstring(z.read('xl/worksheets/sheet1.xml'))
  assert sheet.find('.//m:c[@r="G4"]/m:v',ns).text=='12345.67'
  assert sheet.find('.//m:c[@r="H4"]/m:v',ns).text=='12.35'
  assert sheet.find('.//m:c[@r="L4"]/m:v',ns).text=='16.05'
  assert sheet.find('.//m:autoFilter',ns).get('ref')=='A3:L4'
  assert sheet.find('.//m:pane',ns).get('ySplit')=='3'
  assert not sheet.findall('.//m:f',ns)
 bad=copy.deepcopy(price_payload);bad['rows'][0]['pricePerKm']='NaN'
 assert c.post('/warehouse/api/admin/prices',headers=admin,json=bad).status_code==400
 duplicate=copy.deepcopy(price_payload);duplicate['rows'].append({**duplicate['rows'][0],'sourceRow':8})
 assert c.post('/warehouse/api/admin/prices',headers=admin,json=duplicate).status_code==400
 for auth in [admin,manager]:
  cat=c.get('/warehouse/api/prices',headers=auth).json
  assert len(cat['rows'])==1
  assert cat['rows'][0]['prices']=={'base':'12.35','plus10':'13.58','plus15':'14.20','plus20':'14.81','plus30':'16.05'}
  snapshot=c.get('/warehouse/api/items?show_sold=1',headers=auth).json
  assert snapshot['canViewPrices'] is True
  assert snapshot['items'][0]['prices']['base']=='12.35'
  assert snapshot['items'][2]['prices'] is None
  assert snapshot['groups'][0]['prices']['plus30']=='16.05'
 hidden=c.get('/warehouse/api/items?show_sold=1',headers=stock_user).json
 assert hidden['canViewPrices'] is False and 'priceVersion' not in hidden
 assert all('prices' not in r and 'priceSourceRow' not in r for r in hidden['items']+hidden['groups'])
 assert prices.match_key({'construction':'ОКПД-04А-(1,5)-1/5,0 Ультракабель','rod':'1,0 ЕАА'})==prices.match_key({'construction':'ОКПД-4А-(1.5)-1/5','rod':'1.0 EAA'})
 exact={'construction':'ОКПД-4А-(1,5)-1/5,0','rod':'1.2 ROD'}
 for difference in [{'construction':'ОКПД-4А-(1,5)-1/5,2'},{'construction':'ОКПД-4А-(1,0)-1/5,0'},{'construction':'ОКТ-Д(3,0)П-4А1-1-0-60'}]:
  assert prices.match_key(exact)==prices.match_key(exact|difference)
 for difference in [{'construction':'ОКПД-8А-(1,5)-1/5,0'},{'rod':'1.4 ROD'},{'rod':'1.2 EAA'}]:
  assert prices.match_key(exact)!=prices.match_key(exact|difference)
 assert prices.match_key({'construction':'unknown','rod':'1.2 ROD'}) is None
 assert prices.match_key({'construction':'ОКПД-4А-(1,5)-1/4,8','rod':''}) is None
 # Different cable diameter and load still receive the same rod/fibre price.
 variant=copy.deepcopy(w.snapshot(True))
 variant['items'][0]['construction']='ОКТ-Д(3,0)П-4А1-1-0-60'
 assert prices.decorate(variant,{'role':'manager','login':'fixture'})['items'][0]['prices']['base']=='12.35'
 # Price import cannot change stock versions, reservations, sales or history.
 before=w.snapshot(True);events=w.history()
 assert c.post('/warehouse/api/admin/prices',headers=admin,json=price_payload).status_code==200
 assert w.snapshot(True)['items']==before['items'] and w.history()==events
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
 assert action('release',5,'price-hidden-release1').json['stock']['canViewPrices'] is False
 assert session_client.post('/logout',headers={'X-Requested-With':'OSK-Map'}).status_code==200
 assert session_client.get('/warehouse/api/items').status_code==401
 print('PASS: unified login; warehouse-only route/API restrictions; existing credentials and CRM preserved; import idempotency; grouped/free/reserved/sold reconciliation; 10-second hide and show sold; server authorship; full history; CSRF; atomic rollback; concurrent reserve conflict')
