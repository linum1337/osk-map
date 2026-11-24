"""Krasnodar stock and append-only audit, separate from the CRM tables."""
import hashlib
import json
import re
import time
import unicodedata
from decimal import Decimal, InvalidOperation
from werkzeug.security import generate_password_hash, check_password_hash
import crm_store
import auth_store

AVAILABLE='available'
RESERVED='reserved'
SOLD='sold'
HIDE_DELAY_MS=10000
ACTIONS={'reserve':(AVAILABLE,RESERVED),'release':(RESERVED,AVAILABLE),'sell':((AVAILABLE,RESERVED),SOLD),'restore':(SOLD,AVAILABLE)}
LABELS={AVAILABLE:'В наличии',RESERVED:'В резерве',SOLD:'Продано'}

def now_ms():return time.time_ns()//1000000

def init():
 with crm_store.connect() as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS warehouse_accounts(login TEXT PRIMARY KEY, display_name TEXT NOT NULL, password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
  CREATE TABLE IF NOT EXISTS warehouse_imports(id TEXT PRIMARY KEY, source_name TEXT NOT NULL, source_json TEXT NOT NULL, actor TEXT NOT NULL, created_at INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS warehouse_items(id TEXT PRIMARY KEY, data TEXT NOT NULL, length_milli INTEGER NOT NULL CHECK(length_milli>0), status TEXT NOT NULL CHECK(status IN ('available','reserved','sold')), version INTEGER NOT NULL DEFAULT 1, updated_by TEXT NOT NULL, updated_at INTEGER NOT NULL, reserved_by TEXT, sold_by TEXT, sold_at INTEGER);
  CREATE TABLE IF NOT EXISTS warehouse_history(id INTEGER PRIMARY KEY, item_id TEXT NOT NULL, action TEXT NOT NULL, from_status TEXT, to_status TEXT NOT NULL, actor TEXT NOT NULL, actor_role TEXT NOT NULL, created_at INTEGER NOT NULL, comment TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE);
  CREATE INDEX IF NOT EXISTS warehouse_history_item ON warehouse_history(item_id,id);
  ''')
  if 'order_number' not in {r[1] for r in c.execute('PRAGMA table_info(warehouse_history)')}:c.execute("ALTER TABLE warehouse_history ADD COLUMN order_number TEXT NOT NULL DEFAULT ''")

def users():
 with crm_store.connect() as c:return [r[0] for r in c.execute('SELECT display_name FROM warehouse_accounts WHERE active=1 ORDER BY display_name')]

def identity(login,password=None):
 with crm_store.connect() as c:row=c.execute('SELECT display_name,password_hash FROM warehouse_accounts WHERE login=? AND active=1',(auth_store.normalize(login),)).fetchone()
 if not row or (password is not None and not check_password_hash(row[1],password)):return None,None
 return {'login':row[0],'role':'warehouse','canExport':False},row[1]

def provision(body):
 if not isinstance(body,dict):return 400,{'error':'Некорректная учётная запись'}
 name=body.get('login');hashed=body.get('password_hash');password=body.get('password')
 if not isinstance(name,str) or not 3<=len(name.strip())<=100:return 400,{'error':'Укажите имя и фамилию'}
 name=' '.join(name.split());login=auth_store.normalize(name)
 if not hashed:
  if not isinstance(password,str) or not 6<=len(password)<=128:return 400,{'error':'Пароль должен содержать от 6 до 128 символов'}
  hashed=generate_password_hash(password)
 if not isinstance(hashed,str) or not re.fullmatch(r'scrypt:32768:8:1\$[a-zA-Z0-9]{8,32}\$[a-f0-9]{128}',hashed):return 400,{'error':'Некорректный пароль'}
 with crm_store.connect() as c:
  c.execute('BEGIN IMMEDIATE')
  if c.execute('SELECT 1 FROM accounts WHERE login=?',(login,)).fetchone():return 409,{'error':'Существующий доступ сохранён; отдельная запись не создана'}
  if c.execute('SELECT 1 FROM warehouse_accounts WHERE login=?',(login,)).fetchone():return 200,{'created':False,'login':name}
  c.execute('INSERT INTO warehouse_accounts(login,display_name,password_hash) VALUES(?,?,?)',(login,name,hashed))
 return 201,{'created':True,'login':name}

def product_key(data):
 # Construction describes the cable; rod is part of its specification. Keep all
 # source markings in the summary even when the actual constructions coincide.
 text=data.get('construction') or data.get('marking') or ''
 text=unicodedata.normalize('NFKC',text).casefold()
 text=re.sub(r'\s*(?:ультракабель|ультркабель|ск)\s*$','',text)
 text=re.sub(r'(окпд-)0+(\d)',r'\1\2',text)
 text=re.sub(r'\s+','',text).replace(',','.')
 rod=re.sub(r'\s+','',data.get('rod','').casefold()).replace(',','.').translate(str.maketrans({'е':'e','а':'a'}))
 return hashlib.sha256((text+'|'+rod).encode()).hexdigest()[:20]

def unpack(row):
 id,data,length,status,version,actor,changed,reserver,seller,sold_at=row
 data=json.loads(data)
 return dict(data,id=id,length=length/1000,status=status,statusLabel=LABELS[status],version=version,updatedBy=actor,updatedAt=changed,reservedBy=reserver,soldBy=seller,soldAt=sold_at,hideAt=sold_at+HIDE_DELAY_MS if sold_at is not None else None,productKey=product_key(data))

def snapshot(show_sold=False,clock=None):
 clock=now_ms() if clock is None else clock
 with crm_store.connect() as c:
  c.execute('BEGIN')
  all_rows=[unpack(r) for r in c.execute('SELECT * FROM warehouse_items ORDER BY rowid') if not json.loads(r[1]).get('supersededBy')]
 groups={}
 for r in all_rows:
  key=r['productKey']
  g=groups.setdefault(key,{'key':key,'construction':r.get('construction') or r.get('marking') or 'Без обозначения','rod':r.get('rod',''),'markings':[],'available':0,'reserved':0,'sold':0,'total':0,'items':0})
  if r.get('marking') and r['marking'] not in g['markings']:g['markings'].append(r['marking'])
  g[r['status']]+=round(r['length']*1000);g['total']+=round(r['length']*1000);g['items']+=1
 for g in groups.values():
  for field in ['available','reserved','sold','total']:g[field]/=1000
  g['remaining']=g['available']+g['reserved']
 visible=[r for r in all_rows if show_sold or r['status']!=SOLD or r['hideAt']>clock]
 totals={s:sum(round(r['length']*1000) for r in all_rows if r['status']==s)/1000 for s in LABELS}
 totals.update(items=len(all_rows),remaining=totals['available']+totals['reserved'])
 return {'items':visible,'groups':list(groups.values()),'totals':totals,'serverNow':clock,'hideDelayMs':HIDE_DELAY_MS}

def history(item_id=None):
 with crm_store.connect() as c:
  ids=[];ancestor=item_id
  while ancestor and ancestor not in ids:
   ids.append(ancestor);record=c.execute('SELECT data FROM warehouse_items WHERE id=?',(ancestor,)).fetchone()
   ancestor=json.loads(record[0]).get('parentItemId') if record else None
  where,args=(' WHERE h.item_id IN ('+','.join('?' for _ in ids)+')',tuple(ids)) if ids else ('',())
  rows=c.execute('SELECT h.id,h.item_id,h.action,h.from_status,h.to_status,h.actor,h.actor_role,h.created_at,h.comment,i.data,h.order_number FROM warehouse_history h JOIN warehouse_items i ON i.id=h.item_id'+where+' ORDER BY h.id DESC',args).fetchall()
 return [{'id':id,'itemId':item,'action':action,'fromStatus':old,'toStatus':new,'actor':actor,'actorRole':role,'createdAt':date,'comment':comment,'orderNumber':order,'reel':json.loads(data).get('reel'),'marking':json.loads(data).get('marking')} for id,item,action,old,new,actor,role,date,comment,data,order in rows]

def change(item_id,body,user):
 if not isinstance(body,dict):return 400,{'error':'Некорректное действие'}
 action=body.get('action');version=body.get('version');key=body.get('requestKey');comment=body.get('comment','')
 if not isinstance(action,str) or action not in ACTIONS or type(version) is not int or not isinstance(key,str) or not 16<=len(key)<=100 or not isinstance(comment,str) or len(comment)>5000:return 400,{'error':'Проверьте действие и комментарий'}
 order=body.get('orderNumber','')
 if action=='sell' and (not isinstance(order,str) or not order.strip() or len(order)>200):return 400,{'error':'Укажите номер заказа покупателя (до 200 символов)'}
 if action=='restore' and body.get('confirmed') is not True:return 400,{'error':'Подтвердите возврат повторно'}
 if action=='restore' and not comment.strip():return 400,{'error':'Укажите причину возврата проданной позиции'}
 with crm_store.connect() as c:
  c.execute('BEGIN IMMEDIATE')
  prior=c.execute('SELECT item_id,action,actor FROM warehouse_history WHERE request_key=?',(key,)).fetchone()
  row=c.execute('SELECT * FROM warehouse_items WHERE id=?',(item_id,)).fetchone()
  if not row:return 404,{'error':'Позиция не найдена'}
  if prior:
   if prior!=(item_id,action,user['login']):return 409,{'error':'Повторите действие'}
   return 200,{'item':unpack(row),'serverNow':now_ms(),'repeated':True}
  current=unpack(row)
  if current.get('supersededBy'):return 409,{'error':'Позиция разбита на отдельные катушки. Обновите таблицу.'}
  if current['version']!=version:return 409,{'error':'Позицию уже изменил другой пользователь. Данные обновлены; проверьте их и повторите действие.','item':current}
  allowed,target=ACTIONS[action];allowed=(allowed,) if isinstance(allowed,str) else allowed
  if current['status'] not in allowed:return 409,{'error':'Действие недоступно для текущего статуса','item':current}
  clock=now_ms();reserver=current['reservedBy'];seller=current['soldBy'];sold_at=current['soldAt']
  if action=='reserve':reserver=user['login']
  if action in ('release','restore'):reserver=None;seller=None;sold_at=None
  if action=='sell':seller=user['login'];sold_at=clock
  data=json.loads(row[1])
  if action=='sell':data['orderNumber']=order.strip()
  if action=='restore':data.pop('orderNumber',None)
  c.execute('UPDATE warehouse_items SET data=? WHERE id=?',(json.dumps(data,ensure_ascii=False),item_id))
  c.execute('UPDATE warehouse_items SET status=?,version=version+1,updated_by=?,updated_at=?,reserved_by=?,sold_by=?,sold_at=? WHERE id=?',(target,user['login'],clock,reserver,seller,sold_at,item_id))
  c.execute('INSERT INTO warehouse_history(item_id,action,from_status,to_status,actor,actor_role,created_at,comment,request_key,order_number) VALUES(?,?,?,?,?,?,?,?,?,?)',(item_id,action,current['status'],target,user['login'],user['role'],clock,comment,key,order.strip() if action=='sell' else current.get('orderNumber','')))
  result=unpack(c.execute('SELECT * FROM warehouse_items WHERE id=?',(item_id,)).fetchone())
 return 200,{'item':result,'serverNow':clock}

def import_stock(body,user):
 if not isinstance(body,dict) or body.get('format')!='osk-krasnodar-stock-v1':return 400,{'error':'Неверный формат остатков'}
 rows=body.get('items');source=body.get('source');digest=body.get('sourceDigest')
 if not isinstance(rows,list) or not 1<=len(rows)<=10000 or not isinstance(source,str) or not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):return 400,{'error':'Проверьте источник и позиции'}
 clean=[];seen=set()
 try:
  for row in rows:
   if not isinstance(row,dict) or type(row.get('sourceRow')) is not int or not 1<=row['sourceRow']<=1048576 or row['sourceRow'] in seen:raise ValueError()
   seen.add(row['sourceRow'])
   for key in ('pallet','reel','construction','marking','note','rod','location'):
    if not isinstance(row.get(key),str) or len(row[key])>5000:raise ValueError()
   value=Decimal(str(row['length']))
   if not value.is_finite() or value<=0 or value>Decimal('100000000') or value*1000!=(value*1000).to_integral_value():raise ValueError()
   data={key:row[key] for key in ('pallet','reel','construction','marking','note','rod','location','sourceRow')}
   data.update(source=source,sourceLength=row.get('sourceLength'),sourceUnit=row.get('sourceUnit','м'))
   clean.append((f"krd-{digest[:12]}-{row['sourceRow']}",data,int(value*1000)))
 except (ValueError,KeyError,TypeError,InvalidOperation):return 400,{'error':'Некорректная строка или длина кабеля'}
 with crm_store.connect() as c:
  c.execute('BEGIN IMMEDIATE')
  if c.execute('SELECT 1 FROM warehouse_imports WHERE id=?',(digest,)).fetchone():return 200,{'imported':False,'reason':'Этот файл уже загружен; резервы и продажи сохранены','items':len(clean)}
  if c.execute('SELECT 1 FROM warehouse_items LIMIT 1').fetchone():return 409,{'error':'Остатки уже загружены. Повторная замена не выполняется, чтобы сохранить резервы и историю.'}
  clock=now_ms()
  c.execute('INSERT INTO warehouse_imports VALUES(?,?,?,?,?)',(digest,source,json.dumps(body.get('sourceData',{}),ensure_ascii=False),user['login'],clock))
  for id,data,length in clean:
   c.execute('INSERT INTO warehouse_items(id,data,length_milli,status,updated_by,updated_at) VALUES(?,?,?,?,?,?)',(id,json.dumps(data,ensure_ascii=False),length,AVAILABLE,user['login'],clock))
   c.execute('INSERT INTO warehouse_history(item_id,action,from_status,to_status,actor,actor_role,created_at,comment,request_key) VALUES(?,?,?,?,?,?,?,?,?)',(id,'import',None,AVAILABLE,user['login'],user['role'],clock,'Импорт из '+source,'import:'+id))
 return 201,{'imported':True,'items':len(clean),'length':sum(r[2] for r in clean)/1000}
