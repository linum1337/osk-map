"""Version-checked stock refresh, preserving identities and historical movements."""
from collections import defaultdict
from decimal import Decimal,InvalidOperation
import json,re,sqlite3
import crm_store
import warehouse_store as stock

FIELDS=('pallet','reel','construction','marking','note','rod','location')

def apply(body,user):
 if not isinstance(body,dict) or body.get('format')!='osk-krasnodar-stock-update-v1':return 400,{'error':'Неверный формат обновления'}
 digest=body.get('sourceDigest');source=body.get('source');rows=body.get('items');versions=body.get('expectedVersions')
 if not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest) or not isinstance(source,str) or not 1<=len(source)<=300 or not isinstance(rows,list) or not 1<=len(rows)<=10000 or not isinstance(versions,dict):return 400,{'error':'Проверьте источник, строки и версии'}
 if not all(isinstance(k,str) and type(v) is int for k,v in versions.items()):return 400,{'error':'Некорректные версии позиций'}
 clean=[];seen=set();existing=set();children=defaultdict(list)
 try:
  for r in rows:
   if not isinstance(r,dict) or type(r.get('sourceRow')) is not int or not 1<=r['sourceRow']<=1048576 or r['sourceRow'] in seen:raise ValueError()
   seen.add(r['sourceRow'])
   if not all(isinstance(r.get(k),str) and len(r[k])<=5000 for k in FIELDS):raise ValueError()
   value=Decimal(str(r['length']))
   if not value.is_finite() or not 0<value<=100000000 or value*1000!=(value*1000).to_integral_value():raise ValueError()
   old_id=r.get('existingId');parent=r.get('parentId')
   if old_id and parent or old_id is not None and (not isinstance(old_id,str) or old_id in existing) or parent is not None and not isinstance(parent,str):raise ValueError()
   if old_id:existing.add(old_id)
   id=old_id or f"krd-{digest[:12]}-{r['sourceRow']}"
   data={k:r[k] for k in FIELDS};data.update(sourceRow=r['sourceRow'],source=source,sourceLength=r.get('sourceLength'),sourceUnit=r.get('sourceUnit','м'))
   if parent:data['parentItemId']=parent
   entry=(id,data,int(value*1000),old_id,parent);clean.append(entry)
   if parent:children[parent].append(entry)
 except (KeyError,ValueError,TypeError,InvalidOperation):return 400,{'error':'Некорректная строка остатков'}
 # A private full database copy precedes every attempted non-idempotent refresh.
 with crm_store.connect() as c:
  if c.execute('SELECT 1 FROM warehouse_imports WHERE id=?',(digest,)).fetchone():return 200,{'updated':False,'reason':'Этот файл уже применён'}
  directory=crm_store.DB.parent/'backups';directory.mkdir(mode=0o700,exist_ok=True)
  backup=directory/f'warehouse-before-update-{stock.now_ms()}-{digest[:12]}.sqlite3'
  with sqlite3.connect(backup) as target:c.backup(target)
  backup.chmod(0o600)
  c.execute('BEGIN IMMEDIATE')
  if c.execute('SELECT 1 FROM warehouse_imports WHERE id=?',(digest,)).fetchone():return 200,{'updated':False,'reason':'Этот файл уже применён'}
  current={r[0]:r for r in c.execute('SELECT * FROM warehouse_items') if not json.loads(r[1]).get('supersededBy')}
  if {id:r[4] for id,r in current.items()}!=versions:return 409,{'error':'Остатки изменились после сверки. Обновите план и повторите загрузку.'}
  if existing&children.keys() or existing|children.keys()!=current.keys():return 400,{'error':'Обновление должно учитывать каждую существующую позицию ровно один раз'}
  for parent,parts in children.items():
   if parent not in current or len(parts)<2 or sum(r[2] for r in parts)!=current[parent][2]:return 400,{'error':'Метраж отдельных катушек не совпадает с исходной позицией'}
   if current[parent][3]!=stock.AVAILABLE:return 409,{'error':'Суммарная позиция уже зарезервирована или продана. Разбиение требует отдельной сверки.'}
  for id,data,length,old_id,parent in clean:
   if old_id and length!=current[old_id][2]:return 400,{'error':'Изменение длины существующей катушки требует отдельной сверки'}
   if not old_id and c.execute('SELECT 1 FROM warehouse_items WHERE id=?',(id,)).fetchone():return 409,{'error':'Идентификатор новой катушки уже существует'}
  clock=stock.now_ms();before=[stock.unpack(r) for r in current.values()]
  c.execute('INSERT INTO warehouse_imports VALUES(?,?,?,?,?)',(digest,source,json.dumps({'sourceData':body.get('sourceData',{}),'before':before,'plan':body},ensure_ascii=False),user['login'],clock))
  def event(id,action,old,new,details):
   c.execute('INSERT INTO warehouse_history(item_id,action,from_status,to_status,actor,actor_role,created_at,comment,request_key) VALUES(?,?,?,?,?,?,?,?,?)',(id,action,old,new,user['login'],user['role'],clock,details,'update:'+digest+':'+id))
  for parent,parts in children.items():
   data=json.loads(current[parent][1]);data['supersededBy']=[r[0] for r in parts]
   c.execute('UPDATE warehouse_items SET data=?,version=version+1,updated_by=?,updated_at=? WHERE id=?',(json.dumps(data,ensure_ascii=False),user['login'],clock,parent))
   event(parent,'split',stock.AVAILABLE,stock.AVAILABLE,f'Источник: {source}. Суммарная позиция разбита на {len(parts)} отдельных катушек без изменения метража.')
  for id,data,length,old_id,parent in clean:
   if old_id:
    old=json.loads(current[old_id][1]);merged=old|data;status=current[old_id][3]
    c.execute('UPDATE warehouse_items SET data=?,version=version+1,updated_by=?,updated_at=? WHERE id=?',(json.dumps(merged,ensure_ascii=False),user['login'],clock,id))
    event(id,'update',status,status,'Источник: '+source+'\n'+'\n'.join(label+': '+str(old.get(k) or '—')+' → '+str(merged.get(k) or '—') for k,label in [('pallet','Паллет'),('reel','Катушка'),('construction','Конструкция'),('marking','Маркировка'),('note','Примечание'),('rod','Пруток'),('location','Место хранения')] if old.get(k)!=merged.get(k)))
   else:
    c.execute('INSERT INTO warehouse_items(id,data,length_milli,status,updated_by,updated_at) VALUES(?,?,?,?,?,?)',(id,json.dumps(data,ensure_ascii=False),length,stock.AVAILABLE,user['login'],clock))
    event(id,'import-update',None,stock.AVAILABLE,f'Источник: {source}. Добавлена отдельная катушка №{data["reel"] or "не указан"}, {length/1000:g} м.')
 return 200,{'updated':True,'items':len(clean),'preserved':len(existing),'newItems':len(clean)-len(existing),'splitPositions':len(children),'length':sum(r[2] for r in clean)/1000}
