"""End-to-end private backup, access control and restore into a new directory."""
import os,sys,tempfile,base64,json,tarfile,io,subprocess,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 data=Path(tmp)/'live';data.mkdir()
 password='fixture-Secret-$\\\"-пароль-123!'
 os.environ.update(DATA_DIR=str(data),APP_USER='admin',APP_PASSWORD=password)
 import server,crm_store,auth_store,warehouse_store as stock,warehouse_prices
 from verify_restore import verify
 c=server.app.test_client();endpoint='/api/admin/backup'
 def auth(name,pw):return {'Authorization':'Basic '+base64.b64encode((name+':'+pw).encode()).decode(),'X-Requested-With':'OSK-Map'}
 admin=auth('admin',password)
 assert auth_store.provision({'login':'Тест Новый','password':'fixturepw08'},'admin')[0]==201
 assert stock.provision({'login':'Тест Склад','password':'fixturepw09'})[0]==201
 with crm_store.connect() as db:
  db.execute('INSERT INTO records VALUES(?,?,1)',('backup-client',json.dumps({'officeId':'backup-client','name':'Fixture company','notes':'Manager note retained','status':'В работе'})))
  db.execute('INSERT INTO history(record_id,changes,actor) VALUES(?,?,?)',('backup-client',json.dumps({'notes':'Manager note retained'}),'Тест Новый'))
 row=dict(sourceRow=2,pallet='1',reel='TEST-1',length=100,construction='ОКПД-4А-(1,5)-1/4,8',marking='fixture marking',note='fixture source note',rod='1.2 ROD',location='Fixture storage')
 assert stock.import_stock(dict(format='osk-krasnodar-stock-v1',source='fixture.xlsx',sourceDigest='a'*64,items=[row]),{'login':'admin','role':'admin'})[0]==201
 item=stock.snapshot(True)['items'][0]
 assert stock.change(item['id'],dict(action='sell',version=1,requestKey='backup-sale-request-0001',orderNumber='BACKUP-ORDER-42'),{'login':'Тест Новый','role':'manager'})[0]==200
 assert warehouse_prices.import_prices(dict(format='osk-warehouse-prices-v1',source='fixture-price.xlsx',sourceDigest='b'*64,title='Fixture price',rows=[dict(sourceRow=7,construction=row['construction'],rod=row['rod'],category='Без клея',cableDiameter='4.8',weight='20',type='round',pricePerKm='10000')]),{'login':'admin','role':'admin'})[0]==201
 (data/'modules/suppliers/fixture.json').write_text('{"data":"Supplier data retained"}')
 (data/'modules/transport/terminals-data.json').write_text('[{"city":"Fixture city","name":"Terminal fixture"}]')
 (data/'tiles').mkdir(exist_ok=True);(data/'tiles/cache-canary').write_text('omit cache')
 (data/'backups').mkdir(exist_ok=True);(data/'backups/old-canary').write_text('omit old backup')
 assert c.post(endpoint,json={}).status_code==401
 for user,pw in [('Тест Новый','fixturepw08'),('Тест Склад','fixturepw09')]:assert c.post(endpoint,headers=auth(user,pw),json={}).status_code==403
 assert c.post(endpoint,headers={'Authorization':admin['Authorization']},json={}).status_code==403
 assert c.post(endpoint,headers=admin|{'Origin':'https://other.invalid'},json={}).status_code==403
 response=c.post(endpoint,headers=admin,json={});assert response.status_code==200
 assert response.mimetype=='application/gzip' and response.headers['Cache-Control']=='private, no-store'
 restore=Path(tmp)/'restore';restore.mkdir()
 with tarfile.open(fileobj=io.BytesIO(response.data),mode='r:gz') as archive:
  names=archive.getnames();assert len(names)==len(set(names))
  assert all(n.startswith('osk-portal/') and '..' not in Path(n).parts for n in names)
  assert not any('/.git/' in n or '/data/tiles/' in n or '/data/backups/' in n for n in names)
  assert all(m.isfile() for m in archive.getmembers())
  archive.extractall(restore,filter='data')
 root=restore/'osk-portal';result=verify(root)
 assert result['tables']['accounts']==1 and result['tables']['warehouse_accounts']==1 and result['tables']['warehouse_items']==1 and result['tables']['warehouse_history']==2
 settings=json.loads((root/'data/runtime-settings.json').read_text());assert settings['APP_PASSWORD']==password
 assert (root/'.env').read_text()=='DOMAIN=localhost\n'
 assert (root/'data/session.key').read_text()==(data/'session.key').read_text()
 assert 'data/' in (root/'.dockerignore').read_text()
 assert './data:/data' in (root/'compose.restore.yaml').read_text()
 target=root/'auth_store.py';original=target.read_bytes();target.write_bytes(original+b'\n# corruption\n')
 try:verify(root)
 except ValueError:pass
 else:raise AssertionError('Corrupted backup accepted')
 target.write_bytes(original)
 code=r'''
import os,json,base64,re
from pathlib import Path
os.environ.update(json.loads((Path(os.environ['DATA_DIR'])/'runtime-settings.json').read_text()))
import server,warehouse_store,warehouse_prices
c=server.app.test_client();base='https://restored.example'
def auth(name,pw):return {'Authorization':'Basic '+base64.b64encode((name+':'+pw).encode()).decode()}
assert c.get('/healthz',base_url=base).status_code==200
admin=auth(os.environ['APP_USER'],os.environ['APP_PASSWORD'])
assert c.get('/api/me',base_url=base,headers=admin).json['role']=='admin'
user=auth('Тест Новый','fixturepw08');warehouse=auth('Тест Склад','fixturepw09')
for path in ['/','/transport/','/suppliers/','/companies/','/requests/','/warehouse/']:assert c.get(path,base_url=base,headers=user).status_code==200,path
assert c.get('/api/records',base_url=base,headers=user).json[0]['notes']=='Manager note retained'
assert c.get('/api/records',base_url=base,headers=warehouse).status_code==403
snap=warehouse_store.snapshot(True);assert snap['items'][0]['status']=='sold' and snap['items'][0]['orderNumber']=='BACKUP-ORDER-42'
assert len(warehouse_store.history())==2
assert warehouse_prices.catalogue()['rows'][0]['prices']['base']=='10.00'
text=c.get('/login',base_url=base).get_data(as_text=True);token=re.search('name="csrf" value="([^"]+)"',text)[1]
response=c.post('/login',base_url=base,data={'login':'Тест Новый','password':'fixturepw08','csrf':token})
assert response.status_code==303 and c.get('/api/me',base_url=base).json['role']=='manager'
assert Path(os.environ['DATA_DIR'],'modules/suppliers/fixture.json').read_text()=='{"data":"Supplier data retained"}'
print('Restored app verified')
'''
 env=dict(os.environ,DATA_DIR=str(root/'data'));check=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,capture_output=True,text=True)
 assert check.returncode==0,check.stderr
 assert check.stdout.strip()=='Restored app verified'
 print('PASS site backup: consistent full DB, code/assets/module data, admin settings and session key, hashes and counts, no caches/secrets in image, admin-only and CSRF; extracted app starts on new domain with all users, notes, warehouse orders/history and prices preserved')
