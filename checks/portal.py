import os,sys,tempfile,base64,re,json,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='portal-test-password-1234')
 import server,manage_users,crm_store
 with crm_store.connect() as fixture:fixture.execute('DELETE FROM accounts')
 # Test datasets are deliberately small; no private data needed.
 t=Path(tmp)/'modules/transport';(t/'terminals-data.json').write_text(json.dumps([{'city':'Тест','name':'Тестовая ТК','address':'не настоящий адрес','lat':55,'lon':37}]))
 s=Path(tmp)/'modules/suppliers';(s/'data.js').write_text('const SUPPLIERS=[{"name":"Тестовый поставщик"}];');(s/'suppliers.csv').write_text('name\nTest\n')
 (s/'audit.html').write_text('<!doctype html><html lang="ru"><style>body{margin:0}</style><a href="suppliers.csv" download>CSV</a></html>')
 manage_users.import_users([{'login':'Андрей Логинов','manager':crm_store.MANAGERS[0],'password':'portal-manager-password-123'}])
 c=server.app.test_client()
 def auth(name,pw):return {'Authorization':'Basic '+base64.b64encode(f'{name}:{pw}'.encode()).decode()}
 admin=auth('admin',os.environ['APP_PASSWORD']);manager=auth('Андрей Логинов','portal-manager-password-123')
 for path in ['/','/transport/','/suppliers/','/companies/','/api/records','/suppliers/data.js']:
  assert c.get(path).status_code==401,path
  for headers in [admin,manager]:assert c.get(path,headers=headers).status_code==200,path
 home=c.get('/',headers=admin).get_data(as_text=True)
 for path in ['/transport/','/suppliers/','/companies/']:assert f'href="{path}"' in home
 for path in ['/portal.css','/portal-home.js','/portal-nav.js','/portal-nav.css','/companies/crm.js','/companies/data.js','/suppliers/app.js','/suppliers/networks.js']:
  assert c.get(path,headers=manager).status_code==200,path
 transport=c.get('/transport/',headers=manager).get_data(as_text=True);raw=re.search(r'<script id="terminals-data" type="application/json">(.*?)</script>',transport,re.S)[1]
 assert json.loads(raw)[0]['city']=='Тест'
 assert "script-src 'self'" in transport and 'id="portal-nav"' not in transport # Created by shared JS.
 assert '/portal-nav.js' in transport and '/access.js' in transport
 assert 'Тестовый поставщик' in c.get('/suppliers/data.js',headers=manager).get_data(as_text=True)
 audit=c.get('/suppliers/audit.html',headers=manager).get_data(as_text=True);assert '/portal-nav.css' in audit and '/access.js' in audit and '/portal-nav.js' in audit
 assert c.get('/suppliers/suppliers.csv',headers=admin).status_code==200
 assert c.get('/suppliers/suppliers.csv',headers=manager).status_code==403
 assert c.get('/module-data/transport/terminals-data.json',headers=manager).status_code==404
 assert c.get('/suppliers/../../initial.sqlite3',headers=admin).status_code==404
 assert c.get('/companies',headers=admin).status_code==302
 assert c.get('/index.html',headers=admin).status_code==302
 print('PASS: portal navigation, shared authentication, all three sections, module data injection, admin-only supplier export and path traversal denial')
