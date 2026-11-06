import os,hmac,threading,urllib.request,urllib.error,json,io,shutil,re,secrets,hashlib
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask,request,jsonify,send_from_directory,Response,abort,g,send_file,redirect,session,render_template_string
from werkzeug.middleware.proxy_fix import ProxyFix
import crm_store,auth_store,table_export,head_office,workspace_store,bitrix_import,supplier_catalog,contact_enrichment
ROOT=Path(__file__).resolve().parent
USERNAME=os.environ.get('APP_USER','osk')
PASSWORD=os.environ.get('APP_PASSWORD','')
if len(PASSWORD)<16:raise RuntimeError('Set APP_PASSWORD to a password of at least 16 characters')
crm_store.init()
auth_store.init()
head_office.init()
workspace_store.initialize()
app=Flask(__name__,static_folder=None)
app.config['MAX_CONTENT_LENGTH']=100000
key_file=crm_store.DB.parent/'session.key'
try:
 with key_file.open('x') as key: key.write(secrets.token_hex(32))
 key_file.chmod(0o600)
except FileExistsError:pass
app.secret_key=key_file.read_text().strip()
app.config.update(SESSION_COOKIE_SECURE=True,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_NAME='osk_session')
def revision(marker):return hmac.new(app.secret_key.encode(),marker.encode(),hashlib.sha256).hexdigest()
def account(login,password=None):
 if login==USERNAME:
  if password is not None and hmac.compare_digest(password.encode(),PASSWORD.encode()):return {'login':USERNAME,'role':'admin','canExport':True},revision(PASSWORD)
 if password is not None:
  user=auth_store.authenticate(login,password)
  if not user:return None,None
  login=user['login']
 with crm_store.connect() as c:row=c.execute('SELECT display_name,manager,password_hash FROM accounts WHERE login=? AND active=1',(auth_store.normalize(login),)).fetchone()
 if not row:return None,None
 return {'login':row[0],'manager':row[1],'role':'manager','canExport':False},revision(row[2])
def session_user():
 login=session.get('login')
 if not isinstance(login,str):return None
 if session.get('kind')=='admin':user,rev=({'login':USERNAME,'role':'admin','canExport':True},revision(PASSWORD)) if login==USERNAME else (None,'')
 else:user,rev=account(login)
 return user if user and hmac.compare_digest(session.get('revision',''),rev) else None

# Run only behind the supplied Caddy proxy (one trusted hop).
app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=1)
cache=crm_store.DB.parent/'tiles';cache.mkdir(parents=True,exist_ok=True)
slots=threading.BoundedSemaphore(6)
MODULE_DATA=crm_store.DB.parent/'modules'
for module in ('transport','suppliers'):
 target=MODULE_DATA/module;target.mkdir(parents=True,exist_ok=True)
 bootstrap=ROOT/'module-data'/module
 if bootstrap.is_dir():
  for file in bootstrap.iterdir():
   if file.is_file() and not (target/file.name).exists():shutil.copy2(file,target/file.name)

@app.before_request
def guard():
 if request.path in ('/healthz','/login','/login.css','/assets/osk-logo.png'):return
 g.user=session_user()
 auth=request.authorization
 if not g.user and auth and auth.type.lower()=='basic':g.user,_=account(auth.username or '',auth.password or '')
 if not g.user:
  if request.method=='GET' and request.accept_mimetypes.accept_html and not request.path.startswith('/api/'):
   return redirect('/login?next='+request.path)
  return jsonify(error='Требуется вход'),401
 if request.path in ('/api/bitrix/preview','/api/bitrix/import','/api/contacts/preview','/api/contacts/enrich'):
  if g.user['role']!='admin':return jsonify(error='Импорт доступен только администратору'),403
  request.max_content_length=12_000_000
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
 response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
 response.headers['Cache-Control']='private, max-age=604800' if request.path.startswith('/tiles/') and response.status_code==200 else 'private, no-cache'
 return response
@app.route('/login',methods=['GET','POST'])
def login_page():
 error=''
 if 'login_csrf' not in session:session['login_csrf']=secrets.token_urlsafe(32)
 next_page=request.values.get('next','/')
 if next_page.split('?')[0] not in ('/','/transport/','/suppliers/','/companies/','/requests/'):next_page='/'
 if request.method=='POST':
  origin=request.headers.get('Origin')
  token=request.form.get('csrf','')
  if (origin and origin.rstrip('/')!=request.host_url.rstrip('/')) or not hmac.compare_digest(token,session['login_csrf']):return Response('Обновите страницу входа и повторите попытку',403)
  user,rev=account(request.form.get('login',''),request.form.get('password',''))
  if user:
   session.clear();session.update(login=user['login'],kind=user['role'],revision=rev)
   return redirect(next_page,code=303)
  error='Неверный логин или пароль'
 options=[(USERNAME,'Администратор · '+USERNAME)]+[(name,name) for name in ['Андрей Логинов','Анна Скрынник','Светлана Квашина','Любовь Коровина'] if name!=USERNAME]
 return render_template_string((ROOT/'app/login.html').read_text(),options=options,csrf=session['login_csrf'],next_page=next_page,error=error,selected=request.form.get('login',USERNAME)),401 if error else 200
@app.get('/login.css')
def login_css():return send_from_directory(ROOT/'app','login.css')
@app.post('/logout')
def logout():
 session.clear();return jsonify(ok=True)
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
 try:records,history=crm_store.export_snapshot(ids)
 except KeyError:return jsonify(error='Запись не найдена. Обновите таблицу'),400
 payload=table_export.xlsx_bytes(records,history) if format=='xlsx' else table_export.csv_bytes(records)
 mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if format=='xlsx' else 'text/csv; charset=utf-8'
 return send_file(io.BytesIO(payload),mimetype=mime,as_attachment=True,download_name='Companies.'+format)
@app.get('/api/head-office-requests')
def head_office_rows():return jsonify(head_office.rows())
@app.post('/api/head-office-requests')
def head_office_create():
 status,data=head_office.create(request.get_json(silent=True),g.user['login'])
 return jsonify(data),status
@app.get('/requests/')
def head_office_page():return send_from_directory(ROOT/'app','head-office.html')
@app.get('/requests')
def head_office_redirect():return redirect('/requests/')
@app.post('/api/export/requests/xlsx')
def export_head_office():
 body=request.get_json(silent=True);ids=body.get('ids') if isinstance(body,dict) else None
 if not isinstance(ids,list) or len(ids)>10000 or any(type(id) is not int for id in ids) or len(ids)!=len(set(ids)):return jsonify(error='Некорректная выборка'),400
 try:clients,history=head_office.export_snapshot(ids)
 except KeyError:return jsonify(error='Запрос не найден'),404
 return send_file(io.BytesIO(table_export.xlsx_bytes(clients,history)),mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',as_attachment=True,download_name='Head-office-requests.xlsx')
@app.get('/data.js')
@app.get('/companies/data.js')
def company_data_script():return Response('window.PROVIDERS='+json.dumps(crm_store.rows(),ensure_ascii=False)+';',mimetype='application/javascript')
@app.get('/city-centres.js')
@app.get('/companies/city-centres.js')
def city_centres_script():return Response('window.CITY_CENTRES='+json.dumps(workspace_store.setting('cityCentres',{}),ensure_ascii=False)+';',mimetype='application/javascript')
@app.get('/scope-data.js')
@app.get('/companies/scope-data.js')
def company_scope_script():return Response(workspace_store.scope_script(),mimetype='application/javascript')
@app.get('/scope.js')
@app.get('/companies/scope.js')
def scope_compatibility():return Response('if(!window.inWorkArea)window.inWorkArea=r=>!r.hiddenReason;',mimetype='application/javascript')
@app.post('/api/bitrix/preview')
@app.post('/api/bitrix/import')
def import_bitrix_report():
 payload=request.get_json(silent=True)
 if not isinstance(payload,dict):return jsonify(error='Выберите подготовленный файл импорта Битрикс24 (JSON)'),400
 try:summary=bitrix_import.run(payload,crm_store.DB,ROOT/'app',apply=request.path.endswith('/import'))
 except (ValueError,KeyError,TypeError,AttributeError) as error:return jsonify(error='Не удалось проверить импорт: '+str(error)),400
 return jsonify(summary)
@app.post('/api/contacts/preview')
@app.post('/api/contacts/enrich')
def enrich_public_contacts():
 try:summary=contact_enrichment.run(request.get_json(silent=True),crm_store.DB,apply=request.path.endswith('/enrich'),actor=g.user['login'])
 except (ValueError,TypeError,KeyError,AttributeError) as error:return jsonify(error='Не удалось проверить контакты: '+str(error)),400
 return jsonify(summary)
@app.get('/api/records')
def records():return jsonify(crm_store.rows())
@app.patch('/api/records/<record_id>')
def update(record_id):
 if not record_id.startswith('office-') or not record_id[7:].isdigit():abort(404)
 body=request.get_json(silent=True)
 if not isinstance(body,dict):return jsonify(error='Некорректный запрос'),400
 try:status,data=crm_store.update(record_id,body,actor=g.user['login'])
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
    for host in ('tile.openstreetmap.org',):
     try:
      req=urllib.request.Request(f'https://{host}/{z}/{x}/{y}.png',headers={'User-Agent':'OSK-company-map/1.0 (+https://github.com/freeder1980-svg/osk-map)','Referer':request.headers.get('Referer',request.host_url)})
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
def index():return send_from_directory(ROOT/'app','portal.html')
@app.get('/index.html')
def legacy_index():return redirect('/')
@app.get('/companies')
def companies_redirect():return redirect('/companies/')
@app.get('/companies/')
def companies_index():return send_from_directory(ROOT/'app','index.html')
@app.get('/companies/<path:name>')
def companies_asset(name):return send_from_directory(ROOT/'app',name)
@app.get('/suppliers')
def suppliers_redirect():return redirect('/suppliers/')
@app.get('/suppliers/')
def suppliers_index():return send_from_directory(ROOT/'modules/suppliers','index.html')
@app.get('/suppliers/<path:name>')
def suppliers_file(name):
 if name=='app.js':return send_from_directory(ROOT/'modules/suppliers',name)
 allowed={'data.js','networks.js','networks.json','suppliers.json','suppliers.csv','audit.html','audit.md','site-audit.json'}
 if name not in allowed:abort(404)
 if name in ('data.js','networks.js','suppliers.json','networks.json','suppliers.csv'):
  rows,networks=supplier_catalog.load(MODULE_DATA/'suppliers')
  if name=='suppliers.json':return jsonify(rows)
  if name=='networks.json':return jsonify(networks)
  if name=='suppliers.csv':return Response(supplier_catalog.csv_text(rows),mimetype='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename=suppliers.csv'})
  variable,value=('SUPPLIERS',rows) if name=='data.js' else ('NETWORKS',networks)
  return Response('const '+variable+'='+json.dumps(value,ensure_ascii=False)+';',mimetype='application/javascript')
 file=MODULE_DATA/'suppliers'/name
 if file.is_file():
  if name=='audit.html':
   html=file.read_text()
   css='<link rel="stylesheet" href="/portal-nav.css">'
   html=html.replace('</head>',css+'</head>',1) if '</head>' in html else html.replace('<style>',css+'<style>',1)
   scripts='<script src="/access.js"></script><script src="/portal-nav.js"></script>'
   html=html.replace('</body>',scripts+'</body>',1) if '</body>' in html else html.replace('</html>',scripts+'</html>',1)
   return Response(html,mimetype='text/html')
  return send_from_directory(file.parent,file.name)
 if name=='data.js':return Response('const SUPPLIERS=[];',mimetype='application/javascript')
 if name=='networks.js':return Response('const NETWORKS={};',mimetype='application/javascript')
 if name.endswith('.json'):return jsonify([])
 if name=='audit.html':return Response('<!doctype html><html lang="ru"><meta charset="utf-8"><p>Материалы проверки ещё не загружены.</p><a href="/suppliers/">Назад</a></html>',mimetype='text/html')
 abort(404)
@app.get('/transport')
def transport_redirect():return redirect('/transport/')
@app.get('/transport/')
def transport_index():
 html=(ROOT/'modules/transport/index.html').read_text()
 for id in ('offline-map','offline-towns','terminals-data','gazetteer-data'):
  file=MODULE_DATA/'transport'/(id+'.json')
  if file.is_file():
   payload=file.read_text().replace('</','<\\/')
   pattern=r'(<script\b[^>]*\bid="'+id+r'"[^>]*>)([\s\S]*?)(</script>)'
   html=re.sub(pattern,lambda m:m[1]+payload+m[3],html,count=1)
 return Response(html,mimetype='text/html')
@app.get('/<path:name>')
def static_file(name):return send_from_directory(ROOT/'app',name)
