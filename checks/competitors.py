"""Restricted competition module and product/price integrity."""
import os,sys,tempfile,base64,json
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='competition-fixture-password')
 import server,competitor_catalog as c
 client=server.app.test_client();admin={'Authorization':'Basic '+base64.b64encode(b'admin:competition-fixture-password').decode(),'X-Requested-With':'OSK-Map'}
 assert client.post('/api/admin/accounts',headers=admin,json={'login':'Competition manager','role':'manager','password':'competition-fixture-password'}).status_code==201
 manager={'Authorization':'Basic '+base64.b64encode(b'Competition manager:competition-fixture-password').decode(),'X-Requested-With':'OSK-Map'}
 for path in ['/competitors/','/competitors/competitors.js','/competitors/competitors.css','/competitors/bootstrap.json','/competitors/api/products','/competitors/api/product/missing']:
  assert client.get(path,headers=manager).status_code==403,path
  assert client.get('/companies'+path,headers=manager).status_code==403,path
 assert client.get('/competitors/').status_code==302
 for query in ['', '?q=test', '?q=%25_','?page=no']:
  r=client.get('/competitors/api/products'+query,headers=admin);assert r.status_code==(400 if query=='?page=no' else 200),(query,r.data[:200])
 data=client.get('/competitors/api/products',headers=admin).json;assert len(data['sources'])==33 and data['canRefresh'] is True and len(data['products'])==20
 assert all(not p['prices'] for p in json.loads((root/'app/competitors/bootstrap.json').read_text()))
 src=c.BY_SOURCE['nk'];html='<h1>Муфты</h1><li class="product"><a class="woocommerce-loop-product__link" href="https://nk-groupltd.ru/shop/mufty/test/"><h2 class="woocommerce-loop-product__title">Муфта Тест</h2></a><span class="price"><span class="amount">100,00 ₽</span></span><span class="price ced_cwsm_price">Опт <span class="amount">90,00 ₽</span></span></li>'
 rows,_=c.listing(src,src['seeds'][0],html);assert len(rows)==1 and [p['amount'] for p in rows[0]['prices']]==['100.00','90.00']
 assert not c.safe_url(src,'https://127.0.0.1/a') and not c.safe_url(src,'http://nk-groupltd.ru/a')
 assert c.price('test','100 USD $')['currency']=='USD';assert c.price('test','0 ₽') is None
 p=rows[0];c.save(p);first=client.get('/competitors/api/product/'+p['id'],headers=admin).json;assert len(first['history'])==1
 c.save(p);assert len(client.get('/competitors/api/product/'+p['id'],headers=admin).json['history'])==1
 p={**p,'prices':[c.price('Опт','80 ₽')]};c.save(p);assert len(client.get('/competitors/api/product/'+p['id'],headers=admin).json['history'])==2
 assert client.post('/competitors/api/refresh',headers=manager,json={}).status_code==403
 assert client.post('/competitors/api/refresh',headers={**admin,'Origin':'https://other.invalid'},json={}).status_code==403
 with patch.object(c,'run'):assert client.post('/competitors/api/refresh',headers=admin,json={'sources':['nk']}).status_code==202
 assert client.post('/competitors/api/refresh',headers=admin,json={'sources':['external']}).status_code==400
 assert client.post('/competitors/api/import',headers=admin,json={'products':[{**p,'url':'http://127.0.0.1/x'}]}).status_code==400
 assert client.get('/competitors/api/products',headers=admin).headers['Cache-Control']=='private, no-store'
 print('PASS competition: 33 sources, default admin-only pages/API/assets/aliases, safe product URLs, public tiers/currency/no-zero handling, price history, owner refresh/import, CSRF and no committed price snapshots')
