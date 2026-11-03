import os,hmac,threading,urllib.request,urllib.error
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask,request,jsonify,send_from_directory,Response,abort
from werkzeug.middleware.proxy_fix import ProxyFix
import crm_store
ROOT=Path(__file__).resolve().parent
USERNAME=os.environ.get('APP_USER','osk')
PASSWORD=os.environ.get('APP_PASSWORD','')
if len(PASSWORD)<16:raise RuntimeError('Set APP_PASSWORD to a password of at least 16 characters')
crm_store.init()
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
 if not auth or auth.type.lower()!='basic' or not (hmac.compare_digest((auth.username or '').encode(),USERNAME.encode()) and hmac.compare_digest((auth.password or '').encode(),PASSWORD.encode())):
  return Response('Требуется вход',401,{'WWW-Authenticate':'Basic realm="OSK", charset="UTF-8"'})
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
