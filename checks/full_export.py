import os,sys,tempfile,base64,json,io,zipfile,xml.etree.ElementTree as E
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def rows(z,sheet):
 root=E.fromstring(z.read(f'xl/worksheets/sheet{sheet}.xml'));assert not root.findall('.//s:f',NS)
 return [[c.find('s:is/s:t',NS).text or '' for c in row.findall('s:c',NS)] for row in root.findall('s:sheetData/s:row',NS)]
with tempfile.TemporaryDirectory() as temp:
 os.environ.update(DATA_DIR=temp,APP_USER='admin',APP_PASSWORD='full-export-admin-password-123')
 import server,crm_store,manage_users,table_export
 with crm_store.connect() as db:db.execute('DELETE FROM accounts')
 manage_users.import_users([{'login':'Андрей Логинов','manager':crm_store.MANAGERS[0],'password':'full-export-manager-password-123'}])
 def auth(name,password):return {'Authorization':'Basic '+base64.b64encode(f'{name}:{password}'.encode()).decode(),'X-Requested-With':'OSK-Map'}
 admin=auth('admin',os.environ['APP_PASSWORD']);manager=auth('Андрей Логинов','full-export-manager-password-123');client=server.app.test_client()
 record={'officeId':'office-10000001','name':'Экспорт & проверка','manager':crm_store.MANAGERS[0],'status':'Не обработан','notes':'исходная заметка','services':['Кабель','Строительство'],'lat':0,'local':False,'crmMatches':[{'id':'test-crm','owner':'Тест','row':15,'phone':'0007'}],'futureField':{'arbitrary':'новое поле'},'longField':'А😀'*20000}
 with crm_store.connect() as db:db.execute('INSERT INTO records(id,data,version) VALUES(?,?,1)',(record['officeId'],json.dumps(record)))
 for version,note in [(1,'Первый комментарий менеджера'),(2,'Вторая заметка\nс деталями')]:
  result=client.patch('/api/records/'+record['officeId'],headers=manager,json={'version':version,'changes':{'notes':note,'website':'https://example.invalid','officePhone':'00123','generalPhone':'+70000000000','email':'test@example.invalid','status':'В работе'}});assert result.status_code==200
 body={'ids':[record['officeId']]};assert client.post('/api/export/table/xlsx',headers=manager,json=body).status_code==403
 res=client.post('/api/export/table/xlsx',headers=admin,json=body);assert res.status_code==200
 with zipfile.ZipFile(io.BytesIO(res.data)) as z:
  assert z.testzip() is None
  main=rows(z,1);data=dict(zip(main[0],main[1]));assert data['Заметки']=='Вторая заметка\nс деталями';assert data['Телефон офиса']=='00123';assert data['Статус']=='В работе';assert data['Автор последнего изменения']=='Андрей Логинов'
  assert data['Широта']=='0' and data['Местная компания']=='false';assert json.loads(data['futureField'])==record['futureField'];assert json.loads(data['Совпадения Битрикс24 — все данные (JSON)'])==record['crmMatches']
  history=rows(z,2);assert len(history)==3;headers=history[0];notes=headers.index('Заметки');actor=headers.index('Кто внёс изменение');assert history[1][notes]=='Первый комментарий менеджера';assert history[2][notes]=='Вторая заметка\nс деталями';assert all(row[actor]=='Андрей Логинов' for row in history[1:])
  long=rows(z,3);assert ''.join(row[4] for row in long[1:] if row[2]=='longField')==record['longField']
  for name in z.namelist():E.fromstring(z.read(name))
 Path('/tmp/osk-full-export-check.xlsx').write_bytes(res.data)
 # The export uses current database values even when the client presents no field values.
 assert 'futureField' in table_export.company_table(crm_store.export_snapshot(body['ids'])[0])[0]
 print('PASS: manager saves included, latest values, all raw fields, audit author/time, overwritten notes retained in history, UTF-16 long text without loss, zero/false values, export denial for managers')
