"""Warehouse routes use the portal login and its server-verified identity."""
from pathlib import Path
from flask import Blueprint,request,jsonify,send_from_directory,g,redirect
import warehouse_store as store
import auth_store

ROOT=Path(__file__).resolve().parent/'app/warehouse'

def register(app,admin_name):
 bp=Blueprint('warehouse',__name__,url_prefix='/warehouse')
 @bp.before_request
 def guard():
  if request.path.startswith('/warehouse/api/admin/'):
   if g.user['role']!='admin':return jsonify(error='Доступно только администратору'),403
   request.max_content_length=12_000_000
 @bp.get('/')
 def index():return send_from_directory(ROOT,'index.html')
 @bp.get('')
 def index_redirect():return redirect('/warehouse/')
 @bp.get('/warehouse.css')
 def css():return send_from_directory(ROOT,'warehouse.css')
 @bp.get('/warehouse.js')
 def js():return send_from_directory(ROOT,'warehouse.js')
 @bp.get('/api/items')
 def items():return jsonify(store.snapshot(request.args.get('show_sold')=='1'))
 @bp.post('/api/items/<item_id>/action')
 def change(item_id):
  status,data=store.change(item_id,request.get_json(silent=True),g.user)
  if status==200:data['stock']=store.snapshot(show_sold=True)
  return jsonify(data),status
 @bp.get('/api/history')
 def history():return jsonify(store.history(request.args.get('item') or None))
 @bp.post('/api/admin/users')
 def create_user():
  body=request.get_json(silent=True)
  if isinstance(body,dict) and isinstance(body.get('login'),str) and auth_store.normalize(body['login'])==auth_store.normalize(admin_name):return jsonify(error='Доступ администратора сохранён'),409
  status,data=store.provision(body);return jsonify(data),status
 @bp.post('/api/admin/import')
 def import_items():
  status,data=store.import_stock(request.get_json(silent=True),g.user);return jsonify(data),status
 app.register_blueprint(bp)
