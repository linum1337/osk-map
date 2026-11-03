"""Provision managers: python manage_users.py import < private-users.json"""
import json,sys
from werkzeug.security import generate_password_hash
import crm_store,auth_store

def import_users(payload):
 if not isinstance(payload,list) or len(payload)>100:raise ValueError('Expected a list of manager accounts')
 clean=[];seen=set()
 for row in payload:
  login=row['login'];manager=row['manager'];hashed=row.get('password_hash')
  if not isinstance(login,str) or not 3<=len(login)<=100 or manager not in crm_store.MANAGERS:raise ValueError('Invalid manager account')
  normalized=auth_store.normalize(login)
  if normalized in seen:raise ValueError('Duplicate login')
  seen.add(normalized)
  if not hashed:
   password=row.get('password','')
   if not isinstance(password,str) or len(password)<16:raise ValueError('Password must be at least 16 characters')
   hashed=generate_password_hash(password)
  if not isinstance(hashed,str) or not hashed.startswith(('scrypt:','pbkdf2:')):raise ValueError('Invalid password hash')
  clean.append((normalized,login,manager,hashed))
 crm_store.init();auth_store.init()
 with crm_store.connect() as c:
  for args in clean:c.execute('INSERT OR IGNORE INTO accounts(login,display_name,manager,password_hash) VALUES(?,?,?,?)',args)
 return len(clean)
if __name__=='__main__':
 if sys.argv[1:]!=['import']:raise SystemExit('Usage: python manage_users.py import < private-users.json')
 try:print('Manager accounts processed (existing passwords preserved):',import_users(json.load(sys.stdin)))
 except (ValueError,KeyError,TypeError):raise SystemExit('Invalid manager account input; no account details were printed')
