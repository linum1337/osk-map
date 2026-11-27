"""Administrator account changes and audit. Passwords never enter responses or audit."""
import json,secrets,time
from werkzeug.security import generate_password_hash
import auth_store,crm_store,section_access

ROLE_LABELS={'manager':'Менеджер','warehouse':'Только склад','admin':'Администратор'}

def init():
 with crm_store.connect() as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS admin_account_versions(login TEXT PRIMARY KEY,token TEXT NOT NULL,manager TEXT);
  CREATE TABLE IF NOT EXISTS admin_history(id INTEGER PRIMARY KEY,created_at INTEGER NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,target TEXT NOT NULL,description TEXT NOT NULL,details TEXT NOT NULL,request_key TEXT UNIQUE);
  CREATE TABLE IF NOT EXISTS admin_import_previews(token TEXT PRIMARY KEY,actor TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,summary TEXT NOT NULL,expected_price TEXT,created_at INTEGER NOT NULL,result TEXT);
  ''')

def now():return time.time_ns()//1000000

def revision_token(login):
 with crm_store.connect() as c:row=c.execute('SELECT token FROM admin_account_versions WHERE login=?',(auth_store.normalize(login),)).fetchone()
 return row[0] if row else ''

def record_in(c,actor,action,target,description,details=None,key=None):
 c.execute('INSERT INTO admin_history(created_at,actor,action,target,description,details,request_key) VALUES(?,?,?,?,?,?,?)',(now(),actor,action,target,description,json.dumps(details or {},ensure_ascii=False),key))

def record(actor,action,target,description,details=None,key=None):
 with crm_store.connect() as c:record_in(c,actor,action,target,description,details,key)

def account_rows(c):
 result=[]
 for table,role in [('accounts','manager'),('warehouse_accounts','warehouse')]:
  for login,name,active in c.execute(f'SELECT login,display_name,active FROM {table} ORDER BY display_name'):
   version=c.execute('SELECT token FROM admin_account_versions WHERE login=?',(login,)).fetchone()
   result.append({'login':name,'role':role,'roleLabel':ROLE_LABELS[role],'active':bool(active),'version':version[0] if version else '','protected':False})
 for user in result:user['permissions']=section_access.permissions(user['login'],user['role'],c)
 return result

def users(admin_name):
 with crm_store.connect() as c:rows=account_rows(c)
 return [{'login':admin_name,'role':'admin','roleLabel':ROLE_LABELS['admin'],'active':True,'protected':True,'version':'','permissions':section_access.defaults('admin')}]+rows

def audit(before=None):
 with crm_store.connect() as c:
  sql='SELECT id,created_at,actor,action,target,description FROM admin_history'
  args=()
  if before is not None:sql+=' WHERE id<?';args=(before,)
  rows=c.execute(sql+' ORDER BY id DESC LIMIT 100',args).fetchall()
 return [dict(zip(['id','createdAt','actor','action','target','description'],r)) for r in rows]

def create(body,actor,admin_name):
 if not isinstance(body,dict):return 400,{'error':'Проверьте данные пользователя'}
 name=body.get('login');role=body.get('role');password=body.get('password')
 if not isinstance(name,str) or not 3<=len(name.strip())<=100 or role not in ('manager','warehouse') or not isinstance(password,str) or not 8<=len(password)<=128:return 400,{'error':'Укажите имя и фамилию, доступ и пароль от 8 до 128 символов'}
 name=' '.join(name.split());login=auth_store.normalize(name)
 if login==auth_store.normalize(admin_name):return 409,{'error':'Учётная запись администратора защищена'}
 hashed=generate_password_hash(password)
 with crm_store.connect() as c:
  c.execute('BEGIN IMMEDIATE')
  if c.execute('SELECT 1 FROM accounts WHERE login=? UNION SELECT 1 FROM warehouse_accounts WHERE login=?',(login,login)).fetchone():return 409,{'error':'Пользователь уже существует. Его доступ и пароль сохранены.'}
  if role=='manager':c.execute('INSERT INTO accounts(login,display_name,manager,password_hash) VALUES(?,?,?,?)',(login,name,name,hashed))
  else:c.execute('INSERT INTO warehouse_accounts(login,display_name,password_hash) VALUES(?,?,?)',(login,name,hashed))
  c.execute('INSERT INTO admin_account_versions VALUES(?,?,?)',(login,secrets.token_hex(24),name))
  record_in(c,actor,'user_create',name,'Создан пользователь. Доступ: '+ROLE_LABELS[role],{'role':role})
 return 201,{'ok':True,'login':name}

def change(body,actor,admin_name):
 if not isinstance(body,dict):return 400,{'error':'Проверьте действие'}
 name=body.get('login');action=body.get('action');version=body.get('version')
 if not isinstance(name,str) or not isinstance(version,str) or action not in ('password','active','role','permissions'):return 400,{'error':'Проверьте действие и пользователя'}
 login=auth_store.normalize(name)
 if login==auth_store.normalize(admin_name):return 403,{'error':'Учётная запись администратора защищена от отключения и изменения прав'}
 if action=='permissions' and (not isinstance(body.get('permissions'),dict) or set(body['permissions'])!=section_access.KEYS or any(type(v) is not bool for v in body['permissions'].values())):return 400,{'error':'Проверьте список доступов'}
 if action=='password':
  password=body.get('password')
  if not isinstance(password,str) or not 8<=len(password)<=128:return 400,{'error':'Пароль должен содержать от 8 до 128 символов'}
  new_hash=generate_password_hash(password)
 if action=='active' and type(body.get('active')) is not bool:return 400,{'error':'Укажите состояние доступа'}
 if action=='role' and body.get('role') not in ('manager','warehouse'):return 400,{'error':'Выберите доступ: менеджер или только склад'}
 with crm_store.connect() as c:
  c.execute('BEGIN IMMEDIATE');found=[]
  for table,role in [('accounts','manager'),('warehouse_accounts','warehouse')]:
   row=c.execute(f'SELECT display_name,password_hash,active FROM {table} WHERE login=?',(login,)).fetchone()
   if row:found.append((table,role,row))
  if not found:return 404,{'error':'Пользователь не найден'}
  if len(found)>1:return 409,{'error':'Обнаружены совпадающие учётные записи; требуется сверка'}
  table,role,(display,hashed,active)=found[0]
  profile=c.execute('SELECT token,manager FROM admin_account_versions WHERE login=?',(login,)).fetchone()
  if (profile[0] if profile else '')!=version:return 409,{'error':'Пользователь уже изменён. Обновите список и повторите действие.'}
  if table=='accounts':manager=c.execute('SELECT manager FROM accounts WHERE login=?',(login,)).fetchone()[0]
  else:manager=profile[1] if profile and profile[1] else display
  details={}
  if action=='password':
   c.execute(f'UPDATE {table} SET password_hash=? WHERE login=?',(new_hash,login));description='Изменён пароль. Прежние сеансы входа завершены.';details={'passwordChanged':True}
  elif action=='active':
   if bool(active)==body['active']:return 200,{'ok':True,'unchanged':True}
   c.execute(f'UPDATE {table} SET active=? WHERE login=?',(int(body['active']),login));description='Вход включён' if body['active'] else 'Вход отключён. Данные и история пользователя сохранены.';details={'active':body['active']}
  elif action=='permissions':
   before=section_access.permissions(login,role,c)
   c.execute('INSERT INTO user_section_access VALUES(?,?) ON CONFLICT(login) DO UPDATE SET permissions=excluded.permissions',(login,json.dumps(body['permissions'])))
   description='Изменены доступы к разделам. Прежние сеансы входа завершены.';details={'before':before,'after':body['permissions']}
  else:
   new_role=body['role']
   if new_role==role:return 200,{'ok':True,'unchanged':True}
   c.execute(f'DELETE FROM {table} WHERE login=?',(login,))
   if new_role=='manager':c.execute('INSERT INTO accounts(login,display_name,manager,password_hash,active) VALUES(?,?,?,?,?)',(login,display,manager,hashed,active))
   else:c.execute('INSERT INTO warehouse_accounts(login,display_name,password_hash,active) VALUES(?,?,?,?)',(login,display,hashed,active))
   description='Изменён доступ: '+ROLE_LABELS[role]+' → '+ROLE_LABELS[new_role]+'. Прежние сеансы входа завершены.';details={'fromRole':role,'toRole':new_role}
  c.execute('INSERT INTO admin_account_versions VALUES(?,?,?) ON CONFLICT(login) DO UPDATE SET token=excluded.token,manager=excluded.manager',(login,secrets.token_hex(24),manager))
  record_in(c,actor,'user_'+action,display,description,details)
 return 200,{'ok':True}
