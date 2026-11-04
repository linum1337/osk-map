from pathlib import Path
import sys,sqlite3,json,tempfile,copy,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import bitrix_import
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);app=root/'app';app.mkdir();db=root/'crm.sqlite3'
 (app/'scope.js').write_text('window.VISIBLE_OFFICE_IDS=new Set(["office-1"]);')
 (app/'city-centres.js').write_text('window.CITY_CENTRES={};')
 original={'officeId':'office-1','id':'sample','name':'Тестовая сеть','city':'Кострома','region':'Костромская область','district':'Центральный','manager':'Логинов Андрей','lat':57.7,'lon':40.9,'address':'Проверенный адрес','notes':'Записал менеджер','email':'','website':'https://manager.example.invalid','status':'В работе','services':['Интернет'],'crmMatches':[{'id':'42','phone':'00123','email':'old@example.invalid','sourceFile':'previous.xlsx'}]}
 with sqlite3.connect(db) as c:
  c.execute('create table records(id text primary key,data text,version integer)');c.execute('create table history(id integer primary key,record_id text,changed_at text default CURRENT_TIMESTAMP,changes text,actor text)');c.execute('insert into records values(?,?,3)',('office-1',json.dumps(original)))
  c.execute('insert into history(record_id,changes,actor) values(?,?,?)',('office-1',json.dumps({'email':''}),'Андрей Логинов'))
 def row(id,name,owner='Скрынник Анна',region='Костромская область',lon=40.9):return {'crmId':str(id),'name':name,'owner':owner,'url':'https://example.invalid/crm/'+str(id),'row':2,'raw':{'Название':name,'E-mail компании':'new@example.invalid','Телефон основного контакта':'+70000000000','Последний комментарий':'Новый комментарий CRM','Отрасль':'Интернет провайдер'},'location':{'city':'Кострома','region':region,'district':'Центральный','lat':57.7,'lon':lon,'address':'Адрес из CRM'},'cities':['Кострома']}
 payload={'format':'osk-bitrix-company-import-v1','date':'2026-11-04','sourceFile':'fixture.xlsx','sheet':'Компании без дублей','companies':[row(42,'Тестовая сеть'),row(43,'Новая местная компания'),row(44,'МТС'),row(45,'Скрытый регион',region='Ростовская область'),row(46,'Восточная компания',lon=65)]}
 before=db.read_bytes();preview=bitrix_import.run(payload,db,app);assert db.read_bytes()==before;assert preview['addedRecords']==3 and preview['managerChangesCount']==1
 result=bitrix_import.run(payload,db,app,True);assert result['addedRecords']==3;assert Path(result['backup']).is_file()
 with sqlite3.connect(db) as c:
  records={id:dict(json.loads(d),version=v) for id,d,v in c.execute('select id,data,version from records')};settings={k:json.loads(v) for k,v in c.execute('select key,value from workspace_settings')}
 r=records['office-1'];assert r['manager']=='Скрынник Анна' and r['version']==4
 for key in ['notes','email','status','website','lat','lon','address']:assert r[key]==original[key],key
 assert r['bitrixLastComment']=='Новый комментарий CRM' and r['crmMatches'][0]['phone']=='+70000000000';assert r['crmPreviousMatches'][0]['phone']=='00123'
 assert 'office-2000043' in settings['visibleIds'] and 'office-2000045' not in settings['visibleIds'] and 'office-2000046' not in settings['visibleIds']
 assert records['office-2000043']['lat'] is None and settings['cityCentres']['office-2000043']['approximate'] is True
 assert 'office-2000044' not in records
 repeated=bitrix_import.run(payload,db,app,True);assert repeated['alreadyImported'] is True
 with sqlite3.connect(db) as c:assert c.execute('select count(*) from records').fetchone()[0]==4
 # Distinct CRM identities with the same name are not merged into an already linked record.
 second=copy.deepcopy(payload);second['companies']=[row(99,'Тестовая сеть',owner='Коровина Любовь')]
 result=bitrix_import.run(second,db,app,True);assert result['addedRecords']==1 and result['reviewCount']==1
 with sqlite3.connect(db) as c:assert json.loads(c.execute("select data from records where id='office-1'").fetchone()[0])['manager']=='Скрынник Анна'
 print('PASS: read-only preview, CRM ID ownership, manager edits preserved, all CRM metadata, exclusion policies, city-centre approximation, backup, idempotency, separate CRM identities')
# A Git-only deployment can bootstrap existing city markers and visibility from the captured site.
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);app=root/'app';app.mkdir();db=root/'crm.sqlite3'
 with sqlite3.connect(db) as c:
  c.execute('create table records(id text primary key,data text,version integer)');c.execute('create table history(id integer primary key,record_id text,changed_at text default CURRENT_TIMESTAMP,changes text,actor text)')
  c.execute('insert into records values(?,?,1)',('office-1',json.dumps(original)))
 prepared=copy.deepcopy(payload);prepared['companies']=[row(42,'Тестовая сеть')];prepared['workspaceBootstrap']={'visibleIds':['office-1'],'cityCentres':{'office-1':{'city':'Кострома','lat':57.7,'lon':40.9,'region':'Костромская область'},'unknown-record':{'lat':0,'lon':0}}}
 bitrix_import.run(prepared,db,app,True)
 with sqlite3.connect(db) as c:settings={k:json.loads(v) for k,v in c.execute('select key,value from workspace_settings')}
 assert settings['visibleIds']==['office-1'] and settings['cityCentres']['office-1']['lat']==57.7 and 'unknown-record' not in settings['cityCentres']
 without=copy.deepcopy(prepared);without.pop('workspaceBootstrap');assert bitrix_import.run(without,db,app,True)['alreadyImported'] is True
 print('PASS: hosted city centres/visibility preserved across Git-only deployment, no unknown-record markers, stable import identity')
