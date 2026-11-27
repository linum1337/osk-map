"""Administrator dashboard endpoints and protected static assets."""
from pathlib import Path
from flask import Blueprint,g,request,jsonify,send_from_directory,redirect
import admin_store,admin_imports,crm_store,warehouse_store,section_access

ROOT=Path(__file__).resolve().parent/'app/admin'

def register(app,admin_name):
 bp=Blueprint('administration',__name__)
 @bp.before_request
 def protect():
  if not section_access.has(g.user,'administration'):return jsonify(error='Раздел доступен только администратору'),403
 @bp.get('/admin')
 def root_redirect():return redirect('/admin/')
 @bp.get('/admin/')
 def index():return send_from_directory(ROOT,'index.html')
 @bp.get('/admin/admin.css')
 def css():return send_from_directory(ROOT,'admin.css')
 @bp.get('/admin/admin.js')
 def js():return send_from_directory(ROOT,'admin.js')
 @bp.get('/api/admin/overview')
 def overview():
  with crm_store.connect() as c:
   companies=c.execute('SELECT COUNT(*) FROM records').fetchone()[0]
   history=c.execute('SELECT COUNT(*) FROM warehouse_history').fetchone()[0]
  users=admin_store.users(admin_name);totals=warehouse_store.snapshot()['totals']
  return jsonify(companies=companies,users=sum(r['active'] for r in users),warehouse=totals,warehouseHistory=history)
 @bp.get('/api/admin/accounts')
 def users():return jsonify(admin_store.users(admin_name))
 @bp.post('/api/admin/accounts')
 def create():
  status,data=admin_store.create(request.get_json(silent=True),g.user['login'],admin_name);return jsonify(data),status
 @bp.post('/api/admin/accounts/change')
 def change():
  status,data=admin_store.change(request.get_json(silent=True),g.user['login'],admin_name);return jsonify(data),status
 @bp.get('/api/admin/sections')
 def sections():return jsonify([{'id':k,'label':v} for k,v in section_access.SECTIONS])
 @bp.get('/api/admin/audit')
 def audit():
  before=request.args.get('before')
  if before is not None:
   try:before=int(before)
   except ValueError:return jsonify(error='Некорректная страница журнала'),400
   if not 0<before<2**63:return jsonify(error='Некорректная страница журнала'),400
  return jsonify(admin_store.audit(before))
 @bp.post('/api/admin/import/preview')
 def import_preview():
  request.max_content_length=12_000_000
  file=request.files.get('file')
  if not file:return jsonify(error='Выберите Excel-файл'),400
  content=file.stream.read(10_000_001)
  status,data=admin_imports.preview(content,file.filename,request.form.get('kind'),g.user['login'])
  return jsonify(data),status
 @bp.post('/api/admin/import/apply')
 def import_apply():
  status,data=admin_imports.apply(request.get_json(silent=True),g.user['login']);return jsonify(data),status
 app.register_blueprint(bp)
