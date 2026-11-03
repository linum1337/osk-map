import os,sys,tempfile,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='login-test-admin-password-123')
 import server,manage_users,crm_store
 with crm_store.connect() as db:db.execute('DELETE FROM accounts')
 manage_users.import_users([{'login':'Андрей Логинов','manager':crm_store.MANAGERS[0],'password':'login-test-manager-password-123'}])
 c=server.app.test_client();base='https://portal.example.ru'
 def get(path,**kwargs):return c.get(path,base_url=base,**kwargs)
 def csrf():
  page=get('/login');assert page.status_code==200
  text=page.get_data(as_text=True)
  assert len(re.findall('<option ',text))==5 and 'Администратор' in text
  return re.search(r'name="csrf" value="([^"]+)"',text)[1]
 def post(data,headers=None):return c.post('/login',base_url=base,data=data,headers=headers or {})
 r=get('/',headers={'Accept':'text/html'});assert r.status_code==302 and '/login' in r.location
 assert get('/api/me').status_code==401
 token=csrf();assert post({'login':'admin','password':os.environ['APP_PASSWORD']}).status_code==403
 assert post({'login':'admin','password':os.environ['APP_PASSWORD'],'csrf':token},headers={'Origin':'https://evil.invalid'}).status_code==403
 r=post({'login':'admin','password':os.environ['APP_PASSWORD'],'csrf':token,'next':'//evil.invalid'});assert r.status_code==303 and r.location=='/'
 cookie=r.headers.get('Set-Cookie','');assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=Lax' in cookie
 assert get('/api/me').json['role']=='admin'
 token=csrf();assert post({'login':'admin','password':'login-test-manager-password-123','csrf':token}).status_code==401
 token=csrf();r=post({'login':'Андрей Логинов','password':'login-test-manager-password-123','csrf':token,'next':'/companies/'});assert r.status_code==303 and r.location=='/companies/'
 assert get('/api/me').json['role']=='manager'
 assert c.post('/api/export/table/xlsx',base_url=base,json={'ids':[]},headers={'X-Requested-With':'OSK-Map'}).status_code==403
 assert get('/offices.csv').status_code==403
 with crm_store.connect() as db:db.execute('UPDATE accounts SET active=0')
 assert get('/api/me').status_code==401
 print('PASS: five login options, administrator and manager form sessions, secure cookies, password checks, CSRF, safe redirects, export roles, account revocation')
