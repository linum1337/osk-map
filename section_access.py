"""Per-user section policy; defaults preserve existing access."""
import json,posixpath
import auth_store,crm_store
SECTIONS=[('transport','Транспортные компании'),('suppliers','Поставщики'),('companies','Компании и таблица'),('requests','Запрос в головной офис'),('warehouse','Склад Краснодар'),('prices','Прайс и цены склада'),('references','Справочные материалы'),('referenceCable','Оптический кабель'),('referenceClosures','Муфты оптические'),('training','Обучение'),('administration','Администрирование'),('exports','Выгрузки данных'),('competitors','Продукция и цены конкурентов')]
KEYS={k for k,_ in SECTIONS}
def init():
 with crm_store.connect() as c:c.execute('CREATE TABLE IF NOT EXISTS user_section_access(login TEXT PRIMARY KEY,permissions TEXT NOT NULL)')
def defaults(role):
 enabled=KEYS if role=='admin' else {'transport','suppliers','companies','requests','warehouse','prices','references','referenceCable'} if role=='manager' else {'warehouse'}
 return {k:k in enabled for k in KEYS}
def permissions(login,role,connection=None):
 if role=='admin':return defaults(role)
 if connection is None:
  with crm_store.connect() as c:return permissions(login,role,c)
 row=connection.execute('SELECT permissions FROM user_section_access WHERE login=?',(auth_store.normalize(login),)).fetchone()
 result=defaults(role)
 if row:result.update({k:v for k,v in json.loads(row[0]).items() if k in KEYS and type(v) is bool})
 return result
def has(user,key):return bool(user.get('permissions',defaults(user.get('role'))).get(key,False))
def decorate(user):
 user={**user,'permissions':permissions(user['login'],user['role'])};user['canExport']=has(user,'exports');return user
def canonical(path):
 path=posixpath.normpath('/'+path.lstrip('/'))
 if path.startswith('/companies/'):
  candidate=path[len('/companies'):]
  if candidate.split('/')[1] in {'admin','training','references','warehouse','suppliers','transport','requests','competitors'}:return candidate
 return path
def required(path):
 p=canonical(path)
 if p=='/admin' or p.startswith(('/admin/','/api/admin/')):return ['administration']
 if p=='/warehouse' or p.startswith('/warehouse/'):
  if p.startswith('/warehouse/api/admin/'):return ['warehouse','administration']
  if p.startswith('/warehouse/api/prices'):return ['warehouse','prices']
  return ['warehouse']
 if p=='/references' or p.startswith('/references/'):
  if p.startswith('/references/closures/'):return ['references','referenceClosures']
  if p.startswith('/references/images/') or p.endswith(('/cables.json','/references.js')):return ['references','referenceCable']
  return ['references']
 if p=='/training' or p.startswith('/training/'):return ['training']
 for key in ['transport','suppliers','requests','competitors']:
  if p=='/'+key or p.startswith('/'+key+'/'):return [key]
 if p.startswith('/api/head-office-requests') or p.startswith('/api/export/requests/'):return ['requests']
 if p.startswith(('/api/bitrix/','/api/contacts/')):return ['companies','administration']
 if p.startswith(('/api/records','/api/export/table/')):return ['companies']
 if p in ['/data.js','/city-centres.js','/scope-data.js','/scope.js'] or p=='/companies' or p.startswith('/companies/'):return ['companies']
 return []
def allowed_path(user,path):return all(has(user,k) for k in required(path))
def landing(user):
 if user['role']!='warehouse' or any(has(user,k) for k in ['transport','suppliers','companies','requests','references','training','administration']):return '/'
 return '/warehouse/' if has(user,'warehouse') else '/'
