import sqlite3,json,os,tempfile
from urllib.parse import urlsplit
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DB=Path(os.environ.get('DATA_DIR',str(ROOT/'data')))/'crm.sqlite3'
FIELDS={'manager','website','officePhone','generalPhone','email','status','notes'}
HEAD_OFFICE_STATUS='Отправлен в головной офис'
STATUSES=['Не обработан','В работе','Связались','Предложение отправлено',HEAD_OFFICE_STATUS,'Завершён']
MANAGERS=['Логинов Андрей','Скрынник Анна','Квашина Светлана','Коровина Любовь']
def connect():
 c=sqlite3.connect(DB,timeout=15);c.execute('PRAGMA journal_mode=WAL');return c
def init():
 DB.parent.mkdir(parents=True,exist_ok=True)
 assets=ROOT/'app'
 defaults={'data.js':'window.PROVIDERS=[];', 'city-centres.js':'window.CITY_CENTRES={};', 'scope-data.js':'', 'settlement-coverage.json':'[]', 'settlement-coverage.csv':'Населённый пункт;Регион;Население\n', 'offices.csv':'Компания,Город,Адрес,Менеджер\n', 'providers.csv':'Компания,Город\n'}
 for name,value in defaults.items():
  path=assets/name
  if not path.exists():path.write_text(value,encoding='utf-8')
 # A failed first boot may have left a file without any user tables.
 needs_snapshot=not DB.exists()
 if not needs_snapshot:
  with sqlite3.connect(DB) as existing:
   needs_snapshot=not existing.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
 if needs_snapshot and (ROOT/'initial.sqlite3').is_file():
  with tempfile.TemporaryDirectory(prefix='.bootstrap-',dir=DB.parent) as tmp:
   staged=Path(tmp)/'crm.sqlite3'
   # The bundled snapshot is self-contained and must never create WAL sidecars.
   with sqlite3.connect((ROOT/'initial.sqlite3').as_uri()+'?mode=ro&immutable=1',uri=True) as source, sqlite3.connect(staged) as target:
    source.backup(target)
    target.execute('PRAGMA journal_mode=DELETE')
    if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Initial database is damaged')
   if DB.exists():
    # Retain the empty artifact from an interrupted/failed first boot.
    DB.replace(DB.with_name('crm-before-bootstrap-'+os.urandom(6).hex()+'.sqlite3'))
    for suffix in ('-wal','-shm'):
     sidecar=Path(str(DB)+suffix)
     if sidecar.exists():sidecar.unlink()
   staged.replace(DB)
 with connect() as c:
  c.execute('CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, data TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1)')
  c.execute('CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, record_id TEXT, changed_at TEXT DEFAULT CURRENT_TIMESTAMP, changes TEXT)')
  if 'actor' not in {row[1] for row in c.execute('PRAGMA table_info(history)')}:c.execute("ALTER TABLE history ADD COLUMN actor TEXT NOT NULL DEFAULT ''")
  for r in json.loads((ROOT/'crm-seed.json').read_text()) if (ROOT/'crm-seed.json').exists() else []:
   r.update(status='Не обработан',notes='')
   c.execute('INSERT OR IGNORE INTO records VALUES(?,?,1)',(r['officeId'],json.dumps(r,ensure_ascii=False)))
def rows():
 with connect() as c:return [dict(json.loads(d),version=v) for d,v in c.execute('SELECT data,version FROM records ORDER BY rowid')]
def update(id,body,actor=''):
 changes=body.get('changes',{})
 if not changes or set(changes)-FIELDS or any(not isinstance(v,str) or len(v)>10000 for v in changes.values()):return 400,{'error':'Некорректные поля'}
 if 'manager' in changes and changes['manager'] not in MANAGERS:return 400,{'error':'Выберите менеджера из списка'}
 if 'status' in changes and changes['status'] not in STATUSES:return 400,{'error':'Неизвестный статус'}
 if 'website' in changes:
  changes['website']=changes['website'].strip()
  try:
   u=urlsplit(changes['website'])
   if changes['website'] and (u.scheme not in ('http','https') or not u.hostname or any(c.isspace() for c in changes['website'])):raise ValueError()
  except ValueError:return 400,{'error':'Укажите полный адрес сайта, например https://example.ru'}
 with connect() as c:
  c.execute('BEGIN IMMEDIATE')
  row=c.execute('SELECT data,version FROM records WHERE id=?',(id,)).fetchone()
  if not row:return 404,{'error':'Запись не найдена'}
  d,v=row;d=json.loads(d)
  if body.get('version')!=v:return 409,{'error':'Запись уже изменена другим пользователем. Закройте карточку и откройте обновлённую запись.', 'record':dict(d,version=v)}
  d.update(changes)
  c.execute('UPDATE records SET data=?,version=version+1 WHERE id=?',(json.dumps(d,ensure_ascii=False),id))
  c.execute('INSERT INTO history(record_id,changes,actor) VALUES(?,?,?)',(id,json.dumps(changes,ensure_ascii=False),actor))
 return 200,dict(d,version=v+1)

def export_snapshot(ids):
 with connect() as c:
  c.execute('BEGIN')
  all_records={r['officeId']:dict(r,version=v) for d,v in c.execute('SELECT data,version FROM records') for r in [json.loads(d)]}
  if any(id not in all_records for id in ids):raise KeyError('Record not found')
  records=[all_records[id] for id in ids];history=[]
  for start in range(0,len(ids),500):
   chunk=ids[start:start+500];marks=','.join('?' for id in chunk)
   for id,record_id,date,changes,actor in c.execute('SELECT id,record_id,changed_at,changes,actor FROM history WHERE record_id IN ('+marks+')',chunk):
    history.append({'id':id,'recordId':record_id,'changedAt':date,'actor':actor,'changes':json.loads(changes)})
  history.sort(key=lambda h:h['id'])
  for h in history:
   r=all_records[h['recordId']];r['lastEditedAt']=h['changedAt'];r['lastEditedBy']=h['actor']
 return records,history
