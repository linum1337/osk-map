"""Warehouse routes use the portal login and its server-verified identity."""
from pathlib import Path
from io import BytesIO
from flask import Blueprint,request,jsonify,send_from_directory,g,redirect,send_file
import warehouse_store as store
import warehouse_price_export
import warehouse_update
import warehouse_export
import auth_store
import warehouse_prices as prices

ROOT=Path(__file__).resolve().parent/'app/warehouse'

def register(app,admin_name):
 prices.init()
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
 def items():return jsonify(prices.decorate(store.snapshot(request.args.get('show_sold')=='1'),g.user))
 @bp.post('/api/items/<item_id>/action')
 def change(item_id):
  status,data=store.change(item_id,request.get_json(silent=True),g.user)
  if status==200:data['stock']=prices.decorate(store.snapshot(show_sold=True),g.user)
  return jsonify(data),status
 @bp.get('/api/history')
 def history():return jsonify(store.history(request.args.get('item') or None))
 @bp.get('/api/prices')
 def price_catalogue():
  if not prices.allowed(g.user):return jsonify(error='Цены недоступны для этой учётной записи'),403
  return jsonify(prices.catalogue())
 @bp.get('/api/prices.xlsx')
 def download_prices():
  if not prices.allowed(g.user):return jsonify(error='Скачивание прайса недоступно для этой учётной записи'),403
  catalogue=prices.catalogue()
  if not catalogue['rows']:return jsonify(error='Прайс ещё не загружен'),404
  return send_file(BytesIO(warehouse_price_export.xlsx_bytes(catalogue)),mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',as_attachment=True,download_name='osk-price.xlsx')
 @bp.get('/api/admin/stock.xlsx')
 def download_stock():
  return send_file(BytesIO(warehouse_export.xlsx_bytes()),mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',as_attachment=True,download_name='osk-warehouse-history.xlsx')
 @bp.post('/api/admin/prices')
 def import_prices():
  status,data=prices.import_prices(request.get_json(silent=True),g.user);return jsonify(data),status
 @bp.post('/api/admin/users')
 def create_user():
  body=request.get_json(silent=True)
  if isinstance(body,dict) and isinstance(body.get('login'),str) and auth_store.normalize(body['login'])==auth_store.normalize(admin_name):return jsonify(error='Доступ администратора сохранён'),409
  status,data=store.provision(body);return jsonify(data),status
 @bp.post('/api/admin/update')
 def update_stock():
  status,data=warehouse_update.apply(request.get_json(silent=True),g.user);return jsonify(data),status
 @bp.post('/api/admin/import')
 def import_items():
  status,data=store.import_stock(request.get_json(silent=True),g.user);return jsonify(data),status
 app.register_blueprint(bp)
