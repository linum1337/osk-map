"""Internal head-office queue. A request keeps a complete saved client snapshot."""
import json,sqlite3
import crm_store

def init():
 with crm_store.connect() as c:
  c.execute('CREATE TABLE IF NOT EXISTS head_office_requests(id INTEGER PRIMARY KEY, record_id TEXT NOT NULL, snapshot TEXT NOT NULL, history TEXT NOT NULL, comment TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL DEFAULT \'Новый\', request_key TEXT NOT NULL UNIQUE)')
def unpack(row):
 id,record_id,snapshot,history,comment,author,date,status,key=row
 return {'id':id,'recordId':record_id,'client':json.loads(snapshot),'history':json.loads(history),'comment':comment,'createdBy':author,'createdAt':date,'status':status}
def rows():
 with crm_store.connect() as c:return [unpack(row) for row in c.execute('SELECT * FROM head_office_requests ORDER BY id DESC')]
def create(body,actor):
 if not isinstance(body,dict):return 400,{'error':'Некорректный запрос'}
 record_id=body.get('recordId');comment=body.get('comment','');key=body.get('requestKey')
 if not isinstance(record_id,str) or not isinstance(comment,str) or len(comment)>10000 or not isinstance(key,str) or not 16<=len(key)<=100:return 400,{'error':'Проверьте клиента и комментарий'}
 with crm_store.connect() as c:
  c.execute('BEGIN IMMEDIATE')
  prior=c.execute('SELECT * FROM head_office_requests WHERE request_key=?',(key,)).fetchone()
  if prior:
   if prior[5]!=actor or prior[1]!=record_id:return 409,{'error':'Повторите создание запроса'}
   result=unpack(prior)
   current=c.execute('SELECT data,version FROM records WHERE id=?',(record_id,)).fetchone()
   result['record']=dict(json.loads(current[0]),version=current[1]) if current else None
   return 200,result
  row=c.execute('SELECT data,version FROM records WHERE id=?',(record_id,)).fetchone()
  if not row:return 404,{'error':'Клиент не найден'}
  record=dict(json.loads(row[0]),version=row[1])
  if record.get('status')!=crm_store.HEAD_OFFICE_STATUS:
   changes={'status':crm_store.HEAD_OFFICE_STATUS}
   record.update(changes)
   # Store the status with the request in one transaction. A failed insert rolls
   # both changes back; a retried request above never resets a newer status.
   saved={key:value for key,value in record.items() if key!='version'}
   c.execute('UPDATE records SET data=?,version=version+1 WHERE id=?',(json.dumps(saved,ensure_ascii=False),record_id))
   c.execute('INSERT INTO history(record_id,changes,actor) VALUES(?,?,?)',(record_id,json.dumps(changes,ensure_ascii=False),actor))
   record['version']+=1
  history=[{'id':id,'recordId':rid,'changedAt':date,'changes':json.loads(changes),'actor':author} for id,rid,date,changes,author in c.execute('SELECT id,record_id,changed_at,changes,actor FROM history WHERE record_id=? ORDER BY id',(record_id,))]
  cur=c.execute('INSERT INTO head_office_requests(record_id,snapshot,history,comment,created_by,request_key) VALUES(?,?,?,?,?,?)',(record_id,json.dumps(record,ensure_ascii=False),json.dumps(history,ensure_ascii=False),comment,actor,key))
  result=unpack(c.execute('SELECT * FROM head_office_requests WHERE id=?',(cur.lastrowid,)).fetchone())
 result['record']=record
 return 201,result
def export_snapshot(ids):
 requests={r['id']:r for r in rows()}
 if any(id not in requests for id in ids):raise KeyError()
 clients=[];history=[]
 for id in ids:
  r=requests[id];client=dict(r['client']);client.update(sourceOfficeId=r['recordId'],officeId='request-'+str(id),requestNumber=id,requestComment=r['comment'],requestAuthor=r['createdBy'],requestCreatedAt=r['createdAt'],requestStatus=r['status']);clients.append(client)
  history.extend(dict(h,recordId=client['officeId']) for h in r['history'])
 return clients,history
