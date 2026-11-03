import os,sys,tempfile,base64,json,io,zipfile,xml.etree.ElementTree as E
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='hq-test-admin-password-123')
 import server,crm_store,manage_users,head_office
 with crm_store.connect() as db:db.execute('DELETE FROM accounts')
 manage_users.import_users([{'login':'Андрей Логинов','manager':crm_store.MANAGERS[0],'password':'hq-test-manager-password-123'}])
 def auth(name,password):return {'Authorization':'Basic '+base64.b64encode(f'{name}:{password}'.encode()).decode(),'X-Requested-With':'OSK-Map'}
 admin=auth('admin',os.environ['APP_PASSWORD']);manager=auth('Андрей Логинов','hq-test-manager-password-123');c=server.app.test_client()
 record={'officeId':'office-99999991','name':'Клиент <проверка>','city':'Тест','manager':crm_store.MANAGERS[0],'notes':'сохранено менеджером','officePhone':'00123','crmMatches':[{'id':'crm-test','email':'test@example.invalid'}],'unknown':{'all':'данные'}}
 with crm_store.connect() as db:db.execute('INSERT INTO records(id,data,version) VALUES(?,?,1)',(record['officeId'],json.dumps(record)))
 assert c.patch('/api/records/'+record['officeId'],headers=manager,json={'version':1,'changes':{'notes':'Новая заметка'}}).status_code==200
 body={'recordId':record['officeId'],'comment':'Просьба согласовать условия','requestKey':'test-request-key-123456789','createdBy':'подмена','client':{'name':'подмена'}}
 assert c.post('/api/head-office-requests',json=body).status_code==401
 assert c.post('/api/head-office-requests',headers={k:v for k,v in manager.items() if k!='X-Requested-With'},json=body).status_code==403
 res=c.post('/api/head-office-requests',headers=manager,json=body);assert res.status_code==201,res.data
 row=res.json;assert row['createdBy']=='Андрей Логинов';assert row['client']['name']==record['name'];assert row['client']['unknown']==record['unknown'];assert row['client']['notes']=='Новая заметка';assert row['client']['version']==2;assert row['history'][-1]['actor']=='Андрей Логинов'
 assert c.post('/api/head-office-requests',headers=manager,json=body).json['id']==row['id'];assert len(head_office.rows())==1
 assert c.post('/api/head-office-requests',headers=admin,json=body).status_code==409
 assert c.patch('/api/records/'+record['officeId'],headers=manager,json={'version':2,'changes':{'notes':'После запроса'}}).status_code==200
 assert head_office.rows()[0]['client']['notes']=='Новая заметка'
 assert c.get('/requests/',headers=manager).status_code==200
 assert c.post('/api/export/requests/xlsx',headers=manager,json={'ids':[row['id']]}).status_code==403
 res=c.post('/api/export/requests/xlsx',headers=admin,json={'ids':[row['id']]});assert res.status_code==200
 with zipfile.ZipFile(io.BytesIO(res.data)) as z:
  ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'};root=E.fromstring(z.read('xl/worksheets/sheet1.xml'));rows=[[cell.find('s:is/s:t',ns).text or '' for cell in r.findall('s:c',ns)] for r in root.findall('s:sheetData/s:row',ns)];data=dict(zip(rows[0],rows[1]));assert data['Комментарий для головного офиса']==body['comment'];assert data['Заметки']=='Новая заметка';assert data['Автор запроса']=='Андрей Логинов'
 assert c.post('/api/head-office-requests',headers=manager,json={'recordId':'office-missing','requestKey':'missing-request-1234567'}).status_code==404
 print('PASS: saved full client/history snapshot, server-side authorship, idempotency, persistent request table, frozen snapshot, admin-only full Excel, CSRF')
