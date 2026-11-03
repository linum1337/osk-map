import os,sys,tempfile,base64,json,sqlite3,io,zipfile,xml.etree.ElementTree as E
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
def basic(login,password):return {'Authorization':'Basic '+base64.b64encode(f'{login}:{password}'.encode()).decode()}
with tempfile.TemporaryDirectory() as temp:
 os.environ.update(DATA_DIR=temp,APP_USER='admin',APP_PASSWORD='isolated-admin-password-123')
 import server,manage_users,crm_store
 with crm_store.connect() as fixture:fixture.execute('DELETE FROM accounts')
 password='isolated-manager-password-123';names=['Андрей Логинов','Анна Скрынник','Светлана Квашина','Любовь Коровина']
 manage_users.import_users([{'login':name,'manager':manager,'password':password} for name,manager in zip(names,crm_store.MANAGERS)])
 c=server.app.test_client();admin=basic('admin',os.environ['APP_PASSWORD']);write={'X-Requested-With':'OSK-Map'}
 r={'officeId':'office-1','name':'Тест & компания','manager':crm_store.MANAGERS[0],'officePhone':'00123','notes':'=SUM(1,1)','crmMatches':[]}
 with crm_store.connect() as db:db.execute('INSERT OR REPLACE INTO records(id,data,version) VALUES(?,?,1)',('office-1',json.dumps(r)))
 assert c.get('/api/me').status_code==401
 assert c.get('/api/me',headers=basic(names[0],'wrong')).status_code==401
 assert c.get('/api/me',headers=admin).json['canExport'] is True
 for name in names:
  auth=basic(name,password);me=c.get('/api/me',headers=auth);assert me.status_code==200 and me.json['role']=='manager' and me.json['canExport'] is False
  assert c.get('/api/records',headers=auth).status_code==200
  assert b'"canExport": false' in c.get('/access.js',headers=auth).data
  for path in ['/offices.csv','/providers.csv','/settlement-coverage.csv','/OFFICES.CSV','/fake.xlsx','/fake.zip']:
   assert c.get(path,headers=auth).status_code==403,path
  for fmt in ['csv','xlsx']:
   assert c.post('/api/export/table/'+fmt,json={'ids':['office-1']},headers={**auth,**write}).status_code==403
  assert c.post('/api/export/table/xlsx',json={'ids':['office-1'],'role':'admin'},headers={**auth,**write}).status_code==403
 assert c.get('/api/me',headers=basic('  АНДРЕЙ   ЛОГИНОВ ',password)).status_code==200
 for fmt in ['csv','xlsx']:
  result=c.post('/api/export/table/'+fmt,json={'ids':['office-1']},headers={**admin,**write});assert result.status_code==200,result.data
  assert 'attachment' in result.headers['Content-Disposition']
  if fmt=='xlsx':
   with zipfile.ZipFile(io.BytesIO(result.data)) as z:
    assert z.testzip() is None
    sheet=E.fromstring(z.read('xl/worksheets/sheet1.xml'));ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'};assert not sheet.findall('.//s:f',ns)
    cells={e.attrib['r']:e.find('s:is/s:t',ns).text for e in sheet.findall('.//s:c',ns)};assert cells['K2']=='00123';assert cells['O2']=='=SUM(1,1)'
  else:assert "'=SUM" in result.data.decode('utf-8-sig')
 assert c.post('/api/export/table/xlsx',json={'ids':['office-1']},headers=admin).status_code==403
 assert c.post('/api/export/table/xlsx',json={'ids':['office-1','office-1']},headers={**admin,**write}).status_code==400
 assert c.post('/api/export/table/xlsx',json={'ids':['office-99999999']},headers={**admin,**write}).status_code==400
 result=c.patch('/api/records/office-1',json={'version':1,'changes':{'notes':'manager edit'}},headers={**basic(names[0],password),**write});assert result.status_code==200
 assert c.get('/private-users-import.json',headers=admin).status_code==404
 assert c.get('/api/records',headers=basic('admin',password)).status_code==401
 # Re-import never resets existing account password.
 manage_users.import_users([{'login':names[0],'manager':crm_store.MANAGERS[0],'password':'different-password-123456'}])
 assert c.get('/api/me',headers=basic(names[0],password)).status_code==200
 print('PASS: four UTF-8 manager logins, admin-only exports, direct file denials, CSRF, literal XLSX/CSV, editing preserved, repeat import preserves passwords')
