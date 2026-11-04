"""Merge an offline Bitrix company payload into the portal without replacing user edits."""
from pathlib import Path
from urllib.parse import urlsplit
import argparse,collections,copy,csv,datetime,hashlib,json,os,re,sqlite3,sys,tempfile,unicodedata
MANAGERS=['Логинов Андрей','Скрынник Анна','Квашина Светлана','Коровина Любовь']
EDITABLE={'website','officePhone','generalPhone','email','status','notes'}
INACTIVE=re.compile(r'не\s*работа|не\s*действ|не\s*существ|закрыт|ликвидир|прекратил[аи]?\s+(?:работ|деятельност)',re.I)
NETWORK=re.compile(r'ростелеком|мегафон|билайн|(?<![а-яa-z0-9])(?:мтс|ттк|мгтс|t2|tele2)(?![а-яa-z0-9])|транстелеком|нетбайнет|нет.?бай.?нет|вайфаер|wifire|простор\s*телеком|prostor\s*telecom',re.I)
HIDDEN_REGION=re.compile(r'дагестан|кабардино[\s-]*балкар|чеч|ростов|ингуш',re.I)
def norm(v):
 s=unicodedata.normalize('NFKC',str(v or '')).lower().replace('ё','е');s=re.sub(r'(?<![а-яa-z])(?:ооо|оао|зао|пао|ао|ип|нпф|гк)(?![а-яa-z])',' ',s);return re.sub(r'[^a-zа-я0-9]','',s)
def aliases(v):
 s=re.sub(r'\([^)]*\)','',str(v or ''));return {norm(x) for x in [s,*re.split(r'\s*/\s*|\s*\|\s*',s)] if len(norm(x))>=4}
def phone_set(v):
 nums={re.sub(r'\D','',x)[-10:] for x in re.split(r'[;\n,]',str(v or '')) if len(re.sub(r'\D','',x))>=10}
 return {n for n in nums if not n.startswith('800')}
def clean(v):return '' if v in (None,False,'False','не указана') else str(v).strip()
def joined(*values):return '\n'.join(dict.fromkeys(clean(v) for v in values if clean(v)))
def host(v):
 try:
  value=clean(v);return (urlsplit(value if '://' in value else 'https://'+value).hostname or '').lower().removeprefix('www.')
 except ValueError:return ''
def website(v):
 value=clean(v)
 if not value:return ''
 value=value if '://' in value else 'https://'+value
 return value if urlsplit(value).scheme in ('http','https') and host(value) else ''
def excluded(x):
 name=x['name']
 if re.search('убрать',name,re.I):return 'В названии Битрикс24 указано «убрать»'
 if INACTIVE.search(name):return 'Битрикс24: компания не работает / закрыта'
 if NETWORK.search(name) or (re.search(r'дом[.\s]?ру',name,re.I) and not re.search('ринет',name,re.I)):return 'Ранее согласованное исключение федеральной сети'
 return ''
def visible(r,centres):
 if r.get('hiddenReason') or excluded({'name':r.get('name','')}):return False
 city=r.get('city','');p=centres.get(r['officeId'],{});region=' '.join([r.get('region',''),p.get('region','')])
 if HIDDEN_REGION.search(region) or re.search(r'санкт[\s-]*петербург|^спб$',city,re.I):return False
 lon=r.get('lon') if r.get('lon') is not None else p.get('lon')
 return city=='Екатеринбург' or lon is None or lon<=60.6

def initial_workspace(c,app_dir):
 exists=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspace_settings'").fetchone()
 settings={k:json.loads(v) for k,v in c.execute('SELECT key,value FROM workspace_settings')} if exists else {};ids=settings.get('visibleIds');centres=settings.get('cityCentres')
 if 'visibleIds' not in settings:
  found=set()
  for name in ['scope-data.js','scope.js']:
   p=app_dir/name
   if p.exists():
    m=re.search(r'VISIBLE_OFFICE_IDS\s*=\s*new Set\((\[[\s\S]*?\])\)',p.read_text())
    if m:found.update(json.loads(m[1]))
  ids=sorted(found) if found else None
 if centres is None:
  centres={};p=app_dir/'city-centres.js'
  if p.exists():
   m=re.search(r'window.CITY_CENTRES\s*=\s*([\s\S]*?);?\s*$',p.read_text())
   if m:
    try:centres=json.loads(m[1].rstrip(';'))
    except ValueError:pass
 return set(ids) if ids is not None else None,centres

def meta(x,payload,reason,previous=None):
 raw=x['raw'];previous=previous or {};phone=joined(raw.get('Телефоны компании'),raw.get('Телефоны контактов'),raw.get('Телефон основного контакта'));email=joined(raw.get('E-mail компании'),raw.get('E-mail контактов'),raw.get('E-mail основного контакта'))
 value={'id':x['crmId'],'name':x['name'],'owner':x['owner'],'url':clean(x.get('url')) or previous.get('url',''),'sourceFile':payload['sourceFile'],'sheet':payload['sheet'],'row':x['row'],'period':datetime.date.fromisoformat(payload['date']).strftime('%d.%m.%Y'),'phone':phone or previous.get('phone',''),'email':email or previous.get('email',''),'matchReason':reason,'primaryContact':raw.get('Основной контакт'),'contacts':raw.get('Все контакты')}
 for field in ['phone','email']:
  if not value[field] and previous.get(field):value[field]=previous[field]
  if not (phone if field=='phone' else email) and previous.get(field):value[field+'SourceFile']=previous.get(field+'SourceFile',previous.get('sourceFile'))
 return value

def plan(c,payload,app_dir):
 records={id:dict(json.loads(data),version=version) for id,data,version in c.execute('SELECT id,data,version FROM records')};before=copy.deepcopy(records);scope,centres=initial_workspace(c,app_dir)
 bootstrap=payload.get('workspaceBootstrap') or {}
 if scope is None and isinstance(bootstrap.get('visibleIds'),list):scope={id for id in bootstrap['visibleIds'] if isinstance(id,str) and id in records}
 if not centres and isinstance(bootstrap.get('cityCentres'),dict):
  for id,point in bootstrap['cityCentres'].items():
   if id in records and isinstance(point,dict) and isinstance(point.get('lat'),(int,float)) and isinstance(point.get('lon'),(int,float)) and -90<=point['lat']<=90 and -180<=point['lon']<=180:centres[id]=dict(point,approximate=True)
 old_ids=set(records);by_crm=collections.defaultdict(set);by_alias=collections.defaultdict(set);by_phone=collections.defaultdict(set);by_host=collections.defaultdict(set);edited=collections.defaultdict(set)
 for id,changes in c.execute('SELECT record_id,changes FROM history'):
  try:edited[id].update(set(json.loads(changes))&EDITABLE)
  except (ValueError,TypeError):continue
 for id,r in records.items():
  for m in r.get('crmMatches',[]):
   if m.get('id') is not None:by_crm[str(m['id'])].add(id)
  for a in aliases(r.get('name'))|aliases(r.get('brandName')):by_alias[a].add(id)
  phones=joined(r.get('phone'),r.get('officePhone'),r.get('generalPhone'),*(m.get('phone') for m in r.get('crmMatches',[])))
  for n in phone_set(phones):by_phone[n].add(id)
  if host(r.get('website')):by_host[host(r['website'])].add(id)
 summary={'source':payload['sourceFile'],'date':payload['date'],'reportCompanies':len(payload['companies']),'matchedById':0,'matchedByEvidence':0,'addedCompanies':0,'addedRecords':0,'updatedRecords':0,'managerChanges':[],'excluded':[],'review':[],'unchangedNewerRecords':[],'newVisibleRecords':0}
 consumed=collections.defaultdict(list)
 for x in payload['companies']:
  if x['owner'] not in MANAGERS:summary['review'].append({'id':x['crmId'],'name':x['name'],'reason':'Неизвестный ответственный'});continue
  reason='CRM ID';ids=set(by_crm[x['crmId']]);ex=excluded(x)
  if ids:summary['matchedById']+=1
  elif not ex:
   raw=x['raw'];loc=x['location'];candidates=collections.defaultdict(set)
   for a in aliases(x['name']):
    for id in by_alias[a]:
     if norm(loc['city'])==norm(records[id].get('city')) and loc['city']!='Город не указан':candidates[id].add('Название и город')
   for n in phone_set(joined(raw.get('Телефоны компании'),raw.get('Телефоны контактов'),raw.get('Телефон основного контакта'))):
    for id in by_phone[n]:
     if not loc.get('city') or loc['city']=='Город не указан' or norm(loc['city'])==norm(records[id].get('city')):candidates[id].add('Точный телефон')
   h=host(raw.get('Сайт'))
   if h:
    for id in by_host[h]:
     if norm(loc['city'])==norm(records[id].get('city')) and loc['city']!='Город не указан':candidates[id].add('Сайт и город')
   # A different already linked CRM entity is never silently merged.
   conflicts={id for id in candidates if records[id].get('crmMatches') and x['crmId'] not in {str(m.get('id')) for m in records[id]['crmMatches']}}
   candidates={id:v for id,v in candidates.items() if id not in conflicts}
   entities={records[id].get('key') or records[id].get('id') or id for id in candidates}
   if len(entities)>1 or conflicts:
    summary['review'].append({'id':x['crmId'],'name':x['name'],'reason':'Разные CRM ID / неоднозначное имя: сохранены отдельные карточки','candidates':sorted(set(candidates)|conflicts)})
   if len(entities)>1:candidates={}
   ids=set(candidates)
   if ids:reason='; '.join(sorted(set.union(*candidates.values())));summary['matchedByEvidence']+=1
  if ex:
   summary['excluded'].append({'id':x['crmId'],'name':x['name'],'reason':ex,'existingRecords':sorted(ids)})
   if not ids:continue
  if not ids:
   oid='office-'+str(2_000_000+int(x['crmId']))
   if oid in records:raise ValueError('New record ID collision: '+oid)
   loc=x['location'];r={'id':'bitrix-'+x['crmId'],'officeId':oid,'name':x['name'],'city':loc.get('city') or 'Город не указан','region':loc.get('region') or 'Требует уточнения','district':loc.get('district') or 'Не определён','lat':None,'lon':None,'address':loc.get('address',''),'office':bool(loc.get('address')),'officeType':'Компания из Битрикс24','precision':'Адрес из Битрикс24; координаты офиса не подтверждены','addressStatus':'Адрес из CRM — не проверен' if loc.get('address') else 'Адрес не указан','website':'','source':x.get('url') or '','group':'Компании из Битрикс24','services':['Профиль требует уточнения'],'checked':payload['date'],'visitNote':'Метка условно у центра города; это не координаты офиса. Адрес и приём посетителей уточняйте.','key':'bitrix:'+x['crmId'],'manager':x['owner'],'officePhone':'','generalPhone':'','phone':'','email':'','status':'Не обработан','notes':'','contactSources':[],'crmMatches':[],'fromBitrix':True,'version':1}
   records[oid]=r;ids={oid};reason='Новая компания из выгрузки';summary['addedCompanies']+=1;summary['addedRecords']+=1
  for id in ids:
   r=records[id]
   if r.get('bitrixReportDate','')>payload['date']:summary['unchangedNewerRecords'].append(id);continue
   consumed[id].append(x)
   if len({v['owner'] for v in consumed[id]})>1:raise ValueError('Conflicting CRM owners for one record')
   if ex:r['hiddenReason']=ex
   matches=r.setdefault('crmMatches',[]);previous=next((m for m in matches if str(m.get('id'))==x['crmId']),None);updated=meta(x,payload,reason,previous)
   if previous and previous!=updated and previous not in r.setdefault('crmPreviousMatches',[]):r['crmPreviousMatches'].append(copy.deepcopy(previous))
   r['crmMatches']=[m for m in matches if str(m.get('id'))!=x['crmId']]+[updated]
   raw=x['raw'];r.update(bitrixData=raw,bitrixReportDate=payload['date'],bitrixSource={'file':payload['sourceFile'],'sheet':payload['sheet'],'row':x['row'],'date':payload['date']},bitrixDescription=clean(raw.get('Описание / комментарий')),bitrixLastComment=clean(raw.get('Последний комментарий')),bitrixCommentDate=raw.get('Дата последнего комментария'),bitrixCommentAuthor=raw.get('Автор комментария'),bitrixIndustry=raw.get('Отрасль'),bitrixStatus=raw.get('Статус [UF_CRM_1549960558846]'),bitrixProducts=raw.get('Продукты [UF_CRM_1549961739358]'),bitrixCities=x.get('cities',[]))
   r['crmCheck']='Найдена в отчёте';r['crmReportPeriod']=datetime.date.fromisoformat(payload['date']).strftime('%d.%m.%Y')
   if r.get('manager')!=x['owner']:
    summary['managerChanges'].append({'officeId':id,'name':r['name'],'before':r.get('manager'),'after':x['owner'],'crmId':x['crmId']});r['manager']=x['owner']
   # CRM contacts remain linked to people; only company-level blanks auto-fill portal fields.
   for field,value in [('website',website(raw.get('Сайт'))),('generalPhone',clean(raw.get('Телефоны компании'))),('email',clean(raw.get('E-mail компании')))]:
    if value and not r.get(field) and field not in edited[id]:r[field]=value
   loc=x['location']
   if r.get('fromBitrix'):r['name']=x['name']
   if r.get('city') in ('','Город не указан',None) and loc.get('city')!='Город не указан':r['city']=loc['city'];r['citySource']='Выгрузка Битрикс24 от '+payload['date']
   if r.get('region') in ('','Требует уточнения',None):r['region']=loc.get('region') or 'Требует уточнения'
   if r.get('district') in ('','Не определён',None):r['district']=loc.get('district') or 'Не определён'
   if not r.get('address') and loc.get('address'):
    r['address']=loc['address'];r['addressStatus']='Адрес из CRM — не проверен';r['office']=True
   if r.get('lat') is None and loc.get('lat') is not None and norm(r.get('city'))==norm(loc.get('city')) and id not in centres:centres[id]={'city':loc['city'],'region':loc['region'],'lat':loc['lat'],'lon':loc['lon'],'source':'Справочник города; город указан в Битрикс24','approximate':True}
   if r.get('services') in (None,[],['Профиль требует уточнения'],['Услуги требуют уточнения']) and clean(raw.get('Отрасль')):r['services']=[clean(raw['Отрасль'])]
   if scope is not None:
    if r.get('hiddenReason'):scope.discard(id)
    elif id not in old_ids and visible(r,centres):scope.add(id);summary['newVisibleRecords']+=1
 changes={id:{k:v for k,v in r.items() if k!='version' and (id not in before or before[id].get(k)!=v)} for id,r in records.items() if id not in before or r!=before[id]}
 summary['updatedRecords']=sum(id in before for id in changes);summary['newVisibleRecords']=sum(id not in old_ids and visible(records[id],centres) for id in changes)
 summary['recordsAfter']=len(records);summary['managerChangesCount']=len(summary['managerChanges']);summary['excludedCount']=len(summary['excluded']);summary['reviewCount']=len(summary['review']);summary['visibleAfter']=sum((scope is None or id in scope) and visible(r,centres) for id,r in records.items())
 return records,changes,scope,centres,summary

def run(payload,db,app_dir,apply=False):
 if payload.get('format')!='osk-bitrix-company-import-v1':raise ValueError('Unsupported report format')
 try:report_date=datetime.date.fromisoformat(payload['date'])
 except (ValueError,TypeError,KeyError):raise ValueError('Invalid report date')
 if payload['date']!=report_date.isoformat():raise ValueError('Use an ISO report date')
 if not isinstance(payload.get('companies'),list) or len(payload['companies'])>20000:raise ValueError('Invalid company list')
 ids=[x['crmId'] for x in payload['companies']]
 if len(ids)!=len(set(ids)) or any(not isinstance(id,str) or not id.isdigit() for id in ids):raise ValueError('Duplicate/invalid CRM IDs')
 digest_payload={k:v for k,v in payload.items() if k!='workspaceBootstrap'}
 digest=hashlib.sha256(json.dumps(digest_payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest();db=Path(db)
 if not db.is_file():raise ValueError('Working database not found')
 c=sqlite3.connect(db,timeout=30)
 if apply:c.execute('PRAGMA journal_mode=WAL')
 existing_tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 if 'records' not in existing_tables:
  c.close();raise ValueError('Working database not found')
 if apply:
  backup=db.parent/'backups'/('before-bitrix-'+payload['date']+'-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3');backup.parent.mkdir(exist_ok=True)
  with sqlite3.connect(backup) as dest:c.backup(dest)
 try:
  c.execute('BEGIN IMMEDIATE' if apply else 'BEGIN')
  if apply:
   c.execute('CREATE TABLE IF NOT EXISTS workspace_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
   c.execute('CREATE TABLE IF NOT EXISTS bitrix_import_runs(digest TEXT PRIMARY KEY,report_date TEXT NOT NULL,imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,summary TEXT NOT NULL)')
  has_runs=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bitrix_import_runs'").fetchone()
  prior=c.execute('SELECT summary FROM bitrix_import_runs WHERE digest=?',(digest,)).fetchone() if has_runs else None
  if prior:c.rollback();c.close();return dict(json.loads(prior[0]),alreadyImported=True)
  records,changes,scope,centres,summary=plan(c,payload,Path(app_dir))
  if apply:
   actor='Импорт Битрикс24 '+payload['date'];has_actor='actor' in {r[1] for r in c.execute('PRAGMA table_info(history)')}
   for id,fields in changes.items():
    r=dict(records[id]);version=r.pop('version')
    if c.execute('SELECT 1 FROM records WHERE id=?',(id,)).fetchone():c.execute('UPDATE records SET data=?,version=version+1 WHERE id=?',(json.dumps(r,ensure_ascii=False),id))
    else:c.execute('INSERT INTO records(id,data,version) VALUES(?,?,1)',(id,json.dumps(r,ensure_ascii=False)))
    if has_actor:c.execute('INSERT INTO history(record_id,changes,actor) VALUES(?,?,?)',(id,json.dumps(fields,ensure_ascii=False),actor))
    else:c.execute('INSERT INTO history(record_id,changes) VALUES(?,?)',(id,json.dumps(fields,ensure_ascii=False)))
   for key,value in [('visibleIds',sorted(scope) if scope is not None else None),('cityCentres',centres)]:c.execute('INSERT OR REPLACE INTO workspace_settings VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
   c.execute('INSERT INTO bitrix_import_runs(digest,report_date,summary) VALUES(?,?,?)',(digest,payload['date'],json.dumps(summary,ensure_ascii=False)));c.commit();summary['backup']=str(backup)
  else:c.rollback()
  c.close();return summary
 except Exception:
  c.rollback();raise
 finally:c.close()

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--payload',type=Path);parser.add_argument('--data-dir',type=Path,default=Path(os.environ.get('DATA_DIR','data')));parser.add_argument('--app-dir',type=Path,default=Path.cwd()/'app');parser.add_argument('--apply',action='store_true');parser.add_argument('--report',type=Path);args=parser.parse_args()
 payload=json.loads(args.payload.read_text() if args.payload else sys.stdin.read());summary=run(payload,args.data_dir/'crm.sqlite3',args.app_dir,args.apply)
 if args.report:args.report.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print(json.dumps({k:v for k,v in summary.items() if not isinstance(v,list)},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
