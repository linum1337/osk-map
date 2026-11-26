"""Manager accounts live in the persistent CRM database, never in source control."""
import unicodedata
from werkzeug.security import check_password_hash
import crm_store

def normalize(value):return ' '.join(unicodedata.normalize('NFKC',value).casefold().split())
def init():
 with crm_store.connect() as c:
  c.execute('CREATE TABLE IF NOT EXISTS accounts(login TEXT PRIMARY KEY, display_name TEXT NOT NULL, manager TEXT NOT NULL, password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)')
def authenticate(login,password):
 with crm_store.connect() as c:row=c.execute('SELECT display_name,manager,password_hash FROM accounts WHERE login=? AND active=1',(normalize(login),)).fetchone()
 if not row or not check_password_hash(row[2],password):return None
 return {'login':row[0],'manager':row[1],'role':'manager','canExport':False}

def users():
 with crm_store.connect() as c:return [r[0] for r in c.execute('SELECT display_name FROM accounts WHERE active=1 ORDER BY display_name')]

def provision(body,admin_name):
 from werkzeug.security import generate_password_hash
 import re
 if not isinstance(body,dict) or body.get('role','manager')!='manager':return 400,{'error':'Некорректная учётная запись менеджера'}
 name=body.get('login');password=body.get('password');hashed=body.get('password_hash')
 if not isinstance(name,str) or not 3<=len(name.strip())<=100:return 400,{'error':'Укажите имя и фамилию'}
 name=' '.join(name.split());login=normalize(name);manager=body.get('manager',name)
 if not isinstance(manager,str) or not 3<=len(manager.strip())<=100:return 400,{'error':'Укажите имя менеджера'}
 if not hashed:
  if not isinstance(password,str) or not 6<=len(password)<=128:return 400,{'error':'Пароль должен содержать от 6 до 128 символов'}
  hashed=generate_password_hash(password)
 if not isinstance(hashed,str) or not re.fullmatch(r'scrypt:32768:8:1\$[a-zA-Z0-9]{8,32}\$[a-f0-9]{128}',hashed):return 400,{'error':'Некорректный пароль'}
 if login==normalize(admin_name):return 409,{'error':'Существующий доступ администратора сохранён'}
 with crm_store.connect() as c:
  c.execute('BEGIN IMMEDIATE')
  if c.execute('SELECT 1 FROM warehouse_accounts WHERE login=?',(login,)).fetchone():return 409,{'error':'Существующий складской доступ сохранён'}
  if c.execute('SELECT 1 FROM accounts WHERE login=?',(login,)).fetchone():return 200,{'created':False,'login':name}
  c.execute('INSERT INTO accounts(login,display_name,manager,password_hash) VALUES(?,?,?,?)',(login,name,manager.strip(),hashed))
 return 201,{'created':True,'login':name,'role':'manager'}
