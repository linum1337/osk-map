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
   if prior[5]!=actor:return 409,{'error':'Повторите создание запроса'}
   return 200,unpack(prior)
  row=c.execute('SELECT data,version FROM records WHERE id=?',(record_id,)).fetchone()
  if not row:return 404,{'error':'Клиент не найден'}
  record=dict(json.loads(row[0]),version=row[1]);history=[{'id':id,'recordId':rid,'changedAt':date,'changes':json.loads(changes),'actor':author} for id,rid,date,changes,author in c.execute('SELECT id,record_id,changed_at,changes,actor FROM history WHERE record_id=? ORDER BY id',(record_id,))]
  cur=c.execute('INSERT INTO head_office_requests(record_id,snapshot,history,comment,created_by,request_key) VALUES(?,?,?,?,?,?)',(record_id,json.dumps(record,ensure_ascii=False),json.dumps(history,ensure_ascii=False),comment,actor,key))
  result=unpack(c.execute('SELECT * FROM head_office_requests WHERE id=?',(cur.lastrowid,)).fetchone())
 return 201,result
def export_snapshot(ids):
 requests={r['id']:r for r in rows()}
 if any(id not in requests for id in ids):raise KeyError()
 clients=[];history=[]
 for id in ids:
  r=requests[id];client=dict(r['client']);client.update(sourceOfficeId=r['recordId'],officeId='request-'+str(id),requestNumber=id,requestComment=r['comment'],requestAuthor=r['createdBy'],requestCreatedAt=r['createdAt'],requestStatus=r['status']);clients.append(client)
  history.extend(dict(h,recordId=client['officeId']) for h in r['history'])
 return clients,history
