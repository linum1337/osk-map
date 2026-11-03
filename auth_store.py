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
