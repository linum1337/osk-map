"""Admin UI boundaries, account changes, session revocation, Excel review/apply and audit."""
import os,sys,tempfile,base64,json,re,io,copy,sqlite3
from pathlib import Path
import openpyxl
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='admin-panel-fixture-password')
 import server,crm_store,auth_store,warehouse_store as stock,warehouse_prices as prices,admin_store,admin_imports
 server.app.config['SESSION_COOKIE_SECURE']=False
 c=server.app.test_client()
 def basic(login,pw):return {'Authorization':'Basic '+base64.b64encode((login+':'+pw).encode()).decode(),'X-Requested-With':'OSK-Map'}
 admin=basic('admin',os.environ['APP_PASSWORD']);new={'login':'Тест Менеджер','password':'fixturepw01','role':'manager'}
 def post(path,body,auth=admin):return c.post(path,headers=auth,json=body)
 assert c.get('/admin/',headers={'Accept':'text/html'}).status_code==302
 assert c.get('/api/admin/accounts').status_code==401
 assert post('/api/admin/accounts',new).status_code==201
 assert post('/api/admin/accounts',new).status_code==409
 assert post('/api/admin/accounts',new|{'login':'admin'}).status_code==409
 assert post('/api/admin/accounts',new|{'role':'admin'}).status_code==400
 manager=basic(new['login'],new['password']);assert post('/api/admin/accounts',new|{'login':'Тест Склад','role':'warehouse'}).status_code==201
 warehouse=basic('Тест Склад',new['password'])
 for auth in [manager,warehouse]:
  for path in ['/admin/','/admin/admin.js','/admin/admin.css','/companies/admin/index.html','/companies/admin/admin.js','/api/admin/accounts','/api/admin/overview','/api/admin/audit']:assert c.get(path,headers=auth).status_code==403,path
  assert post('/api/admin/accounts',new,auth).status_code==403
  assert post('/api/admin/import/preview',{},auth).status_code==403
 assert c.get('/admin/',headers=admin).status_code==200
 listed=c.get('/api/admin/accounts',headers=admin).json
 assert listed[0]['protected'] is True
 assert 'password' not in json.dumps(listed).casefold() and 'scrypt' not in json.dumps(listed)
 assert 'no-store' in c.get('/api/admin/accounts',headers=admin).headers['Cache-Control']
 def profile(name):return next(r for r in c.get('/api/admin/accounts',headers=admin).json if r['login']==name)
 def change(name,action,**fields):return post('/api/admin/accounts/change',dict(login=name,action=action,version=profile(name)['version'],**fields))
 def session_login(name,password):
  client=server.app.test_client();text=client.get('/login').get_data(as_text=True);token=re.search('name="csrf" value="([^"]+)"',text)[1]
  assert client.post('/login',data={'login':name,'password':password,'csrf':token}).status_code==303
  return client
 session=session_login(new['login'],new['password'])
 assert session.get('/api/me').json['role']=='manager'
 old=profile(new['login'])
 assert change(new['login'],'active',active=False).status_code==200
 assert session.get('/api/me').status_code==401
 assert change(new['login'],'active',active=True).status_code==200
 assert session.get('/api/me').status_code==401 # old session cannot revive after re-enable
 assert post('/api/admin/accounts/change',dict(login=new['login'],action='active',active=False,version=old['version'])).status_code==409
 assert change(new['login'],'password',password='new-fixture-password').status_code==200
 assert c.get('/api/me',headers=manager).status_code==401
 manager=basic(new['login'],'new-fixture-password');assert c.get('/api/me',headers=manager).json['role']=='manager'
 session=session_login(new['login'],'new-fixture-password')
 assert change(new['login'],'role',role='warehouse').status_code==200
 assert session.get('/api/me').status_code==401
 assert c.get('/api/me',headers=manager).json['role']=='warehouse'
 assert c.get('/api/records',headers=manager).status_code==403
 assert change(new['login'],'role',role='manager').status_code==200
 assert c.get('/api/me',headers=manager).json['role']=='manager'
 for action,fields in [('active',{'active':False}),('password',{'password':'new-admin-password'}),('role',{'role':'warehouse'})]:assert post('/api/admin/accounts/change',dict(login='admin',version='',action=action,**fields)).status_code==403
 assert c.get('/api/me',headers=admin).json['role']=='admin'
 # A legacy manager assignment survives a role round trip.
 assert auth_store.provision({'login':'Тест Старый','manager':crm_store.MANAGERS[0],'password':'legacy-fixture-pw'},'admin')[0]==201
 assert change('Тест Старый','role',role='warehouse').status_code==200
 assert change('Тест Старый','role',role='manager').status_code==200
 assert c.get('/api/me',headers=basic('Тест Старый','legacy-fixture-pw')).json['manager']==crm_store.MANAGERS[0]

 audit=c.get('/api/admin/audit',headers=admin).json
 assert len(audit)>=7 and all(row['actor']=='admin' for row in audit)
 assert 'fixturepw' not in json.dumps(audit) and 'scrypt' not in json.dumps(audit)
 # Every account mutation and its audit entry commit together.
 before=profile(new['login'])
 with crm_store.connect() as db:db.execute("CREATE TRIGGER fail_admin BEFORE INSERT ON admin_history BEGIN SELECT RAISE(ABORT,'fixture'); END")
 try:admin_store.change(dict(login=new['login'],version=before['version'],action='active',active=False),'admin','admin')
 except sqlite3.IntegrityError:pass
 else:raise AssertionError('Expected audit failure')
 assert profile(new['login'])==before
 with crm_store.connect() as db:db.execute('DROP TRIGGER fail_admin')
 # Build small real Excel uploads, not preconverted JSON.
 def stock_file(note='Original note',rows=None):
  w=openpyxl.Workbook();s=w.active;s.append(['Паллет №','№ катушки','Длина/км','Конструкция','Маркировка','Примечание','Пруток','Место хранения'])
  s.append([1,'TEST-1',.1,'ОКПД-4А-(1,5)-1/4,8','ОКПД-4А-(1,5)-1/4,8',note,'1.2 ROD','Fixture'])
  if rows:
   for row in rows:s.append(row)
  out=io.BytesIO();w.save(out);return out.getvalue()
 def upload(content,kind='stock',name='fixture.xlsx'):
  return c.post('/api/admin/import/preview',headers=admin,data={'kind':kind,'file':(io.BytesIO(content),name)},content_type='multipart/form-data')
 assert upload(b'not a workbook').status_code==400
 assert upload(stock_file(),name='fixture.xlsm').status_code==400
 preview=upload(stock_file());assert preview.status_code==200,preview.json
 assert stock.snapshot(True)['totals']['items']==0
 assert post('/api/admin/import/apply',{'token':preview.json['token']}).status_code==400
 token=preview.json['token'];assert post('/api/admin/import/apply',{'token':token,'confirm':True}).status_code==200
 assert stock.snapshot(True)['totals']['available']==100
 assert post('/api/admin/import/apply',{'token':token,'confirm':True}).status_code==200
 assert upload(stock_file()).json['alreadyImported'] is True
 # Preserve an active reservation during file-only metadata updates.
 item=stock.snapshot(True)['items'][0]
 assert stock.change(item['id'],dict(action='reserve',version=1,requestKey='admin-import-reserve-01'),{'login':'Тест Менеджер','role':'manager'})[0]==200
 changed=upload(stock_file('Corrected note'));assert changed.status_code==200,changed.json
 assert changed.json['summary']['changedRows']==1 and changed.json['summary']['changes'][0]['field']=='Примечание'
 result=post('/api/admin/import/apply',{'token':changed.json['token'],'confirm':True});assert result.status_code==200,result.json
 item=stock.snapshot(True)['items'][0];assert item['status']=='reserved' and item['note']=='Corrected note' and item['reservedBy']=='Тест Менеджер'
 # A state change after preview blocks application.
 pending=upload(stock_file('Second correction'));assert pending.status_code==200
 stock.change(item['id'],dict(action='release',version=item['version'],requestKey='admin-import-release-01'),{'login':'Тест Менеджер','role':'manager'})
 assert post('/api/admin/import/apply',{'token':pending.json['token'],'confirm':True}).status_code==409
 # Price workbook retains source rod and category; screen/export can remain shortened.
 def price_file(value):
  w=openpyxl.Workbook();s=w.active;s.cell(3,4,'Цены с НДС до 01.12.2026');s.append([])
  for col,value_ in [(2,'Наименование Ультра'),(3,'Диаметр прутка'),(4,'Диаметр кабеля'),(5,'Вес кг/км'),(6,'тип'),(9,'Цена за 1 км с НДС в рублях')]:s.cell(5,col,value_)
  s.cell(6,2,'Пруток БЕЗ КЛЕЯ')
  for col,value_ in [(2,'ОКПД-4А-(1,5)-1/4,8'),(3,'1.2 ROD'),(4,4.8),(5,20),(6,'круглый'),(9,value)]:s.cell(7,col,value_)
  out=io.BytesIO();w.save(out);return out.getvalue()
 price=upload(price_file(12345),'prices');assert price.status_code==200,price.json
 assert post('/api/admin/import/apply',{'token':price.json['token'],'confirm':True}).status_code==200
 assert prices.catalogue()['rows'][0]['prices']['base']=='12.35'
 preview=upload(price_file(15000),'prices');assert preview.status_code==200
 other=upload(price_file(16000),'prices');assert post('/api/admin/import/apply',{'token':other.json['token'],'confirm':True}).status_code==200
 assert post('/api/admin/import/apply',{'token':preview.json['token'],'confirm':True}).status_code==409
 assert prices.catalogue()['rows'][0]['prices']['base']=='16.00'
 expired=upload(price_file(17000),'prices')
 with crm_store.connect() as db:db.execute('UPDATE admin_import_previews SET created_at=0 WHERE token=?',(expired.json['token'],))
 assert post('/api/admin/import/apply',{'token':expired.json['token'],'confirm':True}).status_code==409
 print('PASS admin: protected UI/APIs; user create/disable/enable/reset/role; old-session revocation and existing login compatibility; no passwords in audit/responses; atomic audit; real XLSX preview/apply, idempotency, reservations preserved, stale state/catalogue and expired previews rejected')
