import os,sys,tempfile,json,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='bitrix-api-admin-password-123')
 import server,manage_users,crm_store
 with crm_store.connect() as c:
  c.execute('DELETE FROM accounts');c.execute('DELETE FROM records');c.execute('DELETE FROM history');c.execute('INSERT OR REPLACE INTO workspace_settings VALUES(?,?)',('visibleIds','[]'))
 manage_users.import_users([{'login':'Андрей Логинов','manager':crm_store.MANAGERS[0],'password':'bitrix-api-manager-password-123'}])
 def headers(login,password):return {'Authorization':'Basic '+base64.b64encode((login+':'+password).encode()).decode(),'X-Requested-With':'OSK-Map'}
 admin=headers('admin',os.environ['APP_PASSWORD']);manager=headers('Андрей Логинов','bitrix-api-manager-password-123');client=server.app.test_client()
 payload={'format':'osk-bitrix-company-import-v1','date':'2026-11-04','sourceFile':'fixture.xlsx','sheet':'Компании без дублей','companies':[{'crmId':'50','name':'Новый клиент','owner':'Коровина Любовь','url':'https://example.invalid/company/50','row':2,'raw':{'Название':'Новый клиент','Последний комментарий':'Текст из Битрикса','Отрасль':'Интернет провайдер'},'location':{'city':'Кострома','region':'Костромская область','district':'Центральный','lat':57.76,'lon':40.93,'address':''},'cities':['Кострома']}]}
 assert client.post('/api/bitrix/import',json=payload).status_code==401
 assert client.post('/api/bitrix/import',headers=manager,json=payload).status_code==403
 assert client.post('/api/bitrix/preview',headers={k:v for k,v in admin.items() if k!='X-Requested-With'},json=payload).status_code==403
 assert client.post('/api/bitrix/import',headers={**admin,'Origin':'https://evil.invalid'},json=payload).status_code==403
 preview=client.post('/api/bitrix/preview',headers=admin,json=payload);assert preview.status_code==200 and preview.json['addedRecords']==1;assert not crm_store.rows()
 result=client.post('/api/bitrix/import',headers=admin,json=payload);assert result.status_code==200 and result.json['addedRecords']==1,result.data
 assert len(crm_store.rows())==1
 rows=json.loads(client.get('/companies/data.js',headers=manager).get_data(as_text=True).removeprefix('window.PROVIDERS=').rstrip(';'));assert rows[0]['bitrixLastComment']=='Текст из Битрикса' and rows[0]['manager']=='Коровина Любовь'
 assert 'office-2000050' in client.get('/companies/scope-data.js',headers=manager).get_data(as_text=True)
 centre=json.loads(client.get('/companies/city-centres.js',headers=manager).get_data(as_text=True).removeprefix('window.CITY_CENTRES=').rstrip(';'));assert centre['office-2000050']['approximate'] is True
 assert client.post('/api/bitrix/import',headers=admin,json=payload).json['alreadyImported'] is True
 assert len(list((Path(tmp)/'backups').glob('before-bitrix-*.sqlite3')))>=1
 assert client.post('/api/bitrix/preview',headers=admin,json={'format':'wrong'}).status_code==400
 print('PASS: admin-only preview/import, CSRF, safe backups, unchanged preview, live persisted company data/scope/centres, complete metadata, idempotency')
