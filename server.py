import os,hmac,threading,urllib.request,urllib.error,json,io
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask,request,jsonify,send_from_directory,Response,abort,g,send_file
from werkzeug.middleware.proxy_fix import ProxyFix
import crm_store,auth_store,table_export
ROOT=Path(__file__).resolve().parent
USERNAME=os.environ.get('APP_USER','osk')
PASSWORD=os.environ.get('APP_PASSWORD','')
if len(PASSWORD)<16:raise RuntimeError('Set APP_PASSWORD to a password of at least 16 characters')
crm_store.init()
auth_store.init()
app=Flask(__name__,static_folder=None)
app.config['MAX_CONTENT_LENGTH']=100000
# Run only behind the supplied Caddy proxy (one trusted hop).
app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=1)
cache=crm_store.DB.parent/'tiles';cache.mkdir(parents=True,exist_ok=True)
slots=threading.BoundedSemaphore(6)
@app.before_request
def guard():
 if request.path=='/healthz':return
 auth=request.authorization
 if not auth or auth.type.lower()!='basic':
  return Response('Требуется вход',401,{'WWW-Authenticate':'Basic realm="OSK", charset="UTF-8"'})
 login,password=auth.username or '',auth.password or ''
 is_admin=hmac.compare_digest(login.encode(),USERNAME.encode()) and hmac.compare_digest(password.encode(),PASSWORD.encode())
 g.user={'login':USERNAME,'role':'admin','canExport':True} if is_admin else auth_store.authenticate(login,password)
 if not g.user:
  return Response('Неверный логин или пароль',401,{'WWW-Authenticate':'Basic realm="OSK", charset="UTF-8"'})
 if (request.path.startswith('/api/export/') or request.path.lower().endswith(('.csv','.xlsx','.xls','.zip'))) and not g.user['canExport']:
  return jsonify(error='Выгрузка доступна только администратору'),403
 if request.method not in ('GET','HEAD','OPTIONS'):
  if request.headers.get('X-Requested-With')!='OSK-Map':return jsonify(error='Недопустимый запрос'),403
  origin=request.headers.get('Origin')
  if origin and origin.rstrip('/')!=request.host_url.rstrip('/'):return jsonify(error='Недопустимый источник'),403
@app.after_request
def headers(response):
 response.headers['X-Content-Type-Options']='nosniff'
 response.headers['X-Frame-Options']='DENY'
 response.headers['Referrer-Policy']='same-origin'
 response.headers['Cache-Control']='private, no-cache'
 return response
@app.get('/healthz')
def health():return jsonify(ok=True)
@app.get('/api/me')
def current_user():return jsonify(g.user)
@app.get('/access.js')
def access_script():
 payload=json.dumps(g.user,ensure_ascii=True).replace('<','\\u003c')
 return Response('window.CURRENT_USER='+payload+';document.documentElement.classList.toggle("is-admin",window.CURRENT_USER.canExport);',mimetype='application/javascript')
@app.post('/api/export/table/<format>')
def export_table(format):
 if format not in ('csv','xlsx'):abort(404)
 body=request.get_json(silent=True)
 ids=body.get('ids') if isinstance(body,dict) else None
 if not isinstance(ids,list) or len(ids)>10000 or any(not isinstance(x,str) for x in ids) or len(set(ids))!=len(ids):return jsonify(error='Некорректная выборка'),400
 available={r['officeId']:r for r in crm_store.rows()}
 if any(x not in available for x in ids):return jsonify(error='Запись не найдена. Обновите таблицу'),400
 records=[available[x] for x in ids]
 payload=table_export.xlsx_bytes(records) if format=='xlsx' else table_export.csv_bytes(records)
 mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if format=='xlsx' else 'text/csv; charset=utf-8'
 return send_file(io.BytesIO(payload),mimetype=mime,as_attachment=True,download_name='Companies.'+format)
@app.get('/api/records')
def records():return jsonify(crm_store.rows())
@app.patch('/api/records/<record_id>')
def update(record_id):
 if not record_id.startswith('office-') or not record_id[7:].isdigit():abort(404)
 body=request.get_json(silent=True)
 if not isinstance(body,dict):return jsonify(error='Некорректный запрос'),400
 try:status,data=crm_store.update(record_id,body)
 except (TypeError,ValueError,AttributeError):return jsonify(error='Некорректные поля'),400
 return jsonify(data),status
@app.get('/tiles/<int:z>/<int:x>/<int:y>.png')
def tile(z,x,y):
 if z>19 or x>=2**z or y>=2**z:abort(400)
 dest=cache/str(z)/str(x)/(str(y)+'.png')
 if not dest.exists():
  if not slots.acquire(timeout=3):abort(503)
  try:
   if not dest.exists():
    for host in ('tile.openstreetmap.org','tile.openstreetmap.fr/hot'):
     try:
      req=urllib.request.Request(f'https://{host}/{z}/{x}/{y}.png',headers={'User-Agent':'OSK-company-map/1.0'})
      with urllib.request.urlopen(req,timeout=10) as r:data=r.read(2000000)
      if not data.startswith(b'\x89PNG\r\n\x1a\n'):continue
      dest.parent.mkdir(parents=True,exist_ok=True)
      # Each thread has its own temporary file; replacement is atomic.
      tmp=dest.with_suffix(f'.{threading.get_ident()}.tmp');tmp.write_bytes(data);tmp.replace(dest);break
     except (urllib.error.URLError,TimeoutError,OSError):continue
  finally:slots.release()
 if not dest.exists():abort(502)
 return send_from_directory(dest.parent,dest.name,mimetype='image/png')
@app.get('/')
def index():return send_from_directory(ROOT/'app','index.html')
@app.get('/<path:name>')
def static_file(name):return send_from_directory(ROOT/'app',name)
