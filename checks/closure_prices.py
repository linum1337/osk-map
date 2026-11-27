"""Price identity, price-tier scope, refresh persistence, and route access."""
import os,sys,tempfile,json,base64
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='price-test-password')
 import server,closure_prices as prices
 def entry(supplier):return {'id':'fixture','name':'Муфта Тест','supplier':supplier,'url':'https://volsip.ru/katalog/test'}
 html='<h1>Муфта Тест</h1><div class="prod_price"><span id="block_price">2 000,50 ₽</span></div><div class="old_price">9000 ₽</div><div itemprop="price" content="99999"></div>'
 assert prices.parse(entry('Volsip'),html)[0]['amount']=='2000.50'
 assert prices.parse(entry('Volsip'),'<div class="jshop_list_product"><div itemprop="price" content="2000"></div></div>')==[]
 try:prices.parse(entry('НАГ'),'<h1>Другой товар</h1>');raise AssertionError('identity mismatch accepted')
 except ValueError:pass
 assert prices.money('0') is None and prices.money('-') is None
 assert not prices.valid_url('https://127.0.0.1/x') and not prices.valid_url('http://ssd.ru/x') and not prices.valid_url('https://ssd.ru:123/x')
 html='<h1>Муфта Тест</h1><div class="product-aside__block_price"><div class="product__price-value">100 ₽ / шт</div><span class="product__price-title">С НДС</span><div class="price-without-nds-tooltip"><div class="data-list__row"><span class="data-list__title">Розница от 1 шт</span><span class="data-list__value">80 ₽</span></div></div><div class="product__price-list"><div class="data-list__row"><span class="data-list__title">Опт от 10 шт</span><span class="data-list__value">90 ₽</span></div></div></div><div class="product__price-value">9999 ₽</div>'
 got=prices.parse(entry('ССД'),html);assert [(p['amount'],p['tax']) for p in got]==[('100.00','С НДС'),('80.00','Без НДС'),('90.00','С НДС')]
 html='<h1>Муфта Тест</h1><div class="item_main_info"><div class="cost"><div class="price_group"><div class="price_name">Базовая цена</div><div class="price_matrix_wrapper"><div class="price" data-currency="RUB"><span class="price_value">100</span></div></div></div><div class="price_group"><div class="price_name">Опт</div><div class="price_matrix_wrapper"><div class="price"><span class="price_value">90</span></div></div></div></div></div><div class="price_group"><span class="price_value">999</span></div>'
 assert [p['label'] for p in prices.parse(entry('Fibertool'),html)]==['Базовая цена','Опт']
 item=next(iter(prices.catalogue().values()))
 with patch.object(prices,'fetch',return_value='<div class="prod_price"><span id="block_price">1234 ₽</span></div>'):
  first=prices.refresh_one(item);assert first['status']=='ok'
 with patch.object(prices,'fetch',side_effect=TimeoutError):
  second=prices.refresh_one(item);assert second['status']=='error' and second['checkedAt']==first['checkedAt'] and second['prices']==first['prices']
 c=server.app.test_client();auth={'Authorization':'Basic '+base64.b64encode(b'admin:price-test-password').decode(),'X-Requested-With':'OSK-Map'}
 path='/references/closures/api/prices';assert c.get(path).status_code==401
 assert c.get(path,headers=auth).status_code==200
 assert c.get(path,headers=auth).json['canRefresh'] is True
 assert c.get(path,headers=auth).json['refreshIntervalSeconds']==86400
 assert c.post('/api/admin/accounts',headers=auth,json={'login':'Price manager','role':'manager','password':'price-test-password'}).status_code==201
 import section_access
 with prices.crm_store.connect() as db:db.execute('INSERT INTO user_section_access VALUES(?,?)',('price manager',json.dumps({k:True for k in section_access.KEYS})))
 manager={'Authorization':'Basic '+base64.b64encode(b'Price manager:price-test-password').decode(),'X-Requested-With':'OSK-Map'}
 assert c.get(path,headers=manager).status_code==200
 assert c.get(path,headers=manager).json['canRefresh'] is False
 assert c.post(path+'/refresh',headers=manager,json={}).status_code==403
 assert c.post(path+'/refresh',headers=auth,json={'ids':['not-in-catalogue']}).status_code==400
 assert c.post(path+'/refresh',headers={**auth,'Origin':'https://other.invalid'},json={}).status_code==403
 with patch.object(prices,'run'):
  assert c.post(path+'/refresh',headers=auth,json={'ids':[item['id']]}).status_code==202
 with prices.crm_store.connect() as db:
  started=db.execute('SELECT started FROM closure_price_jobs ORDER BY started DESC LIMIT 1').fetchone()[0];db.execute("UPDATE closure_price_jobs SET state='completed'")
 assert not prices.schedule_due(started+86399)
 assert prices.schedule_due(started+86400)
 assert c.get(path,headers=auth).headers['Cache-Control']=='private, no-store'
 print('PASS supplier prices: exact product only, VAT/wholesale tiers, no zero prices, safe URLs, failed refresh keeps timestamp, authenticated CSRF-protected refresh')
