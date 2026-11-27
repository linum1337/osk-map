"""Lanset prices must belong to the current product's explicit offers/SKUs."""
import sys,os,tempfile,json,sqlite3
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DATA_DIR']=tmp
 import competitor_catalog as c
 c.init();src=c.BY_SOURCE['lanset'];record=c.make(src,'/test-current/','Кабель текущий');record['properties']={}
 def page(offers,stocks=''):
  return '<main itemscope itemtype="http://schema.org/Product"><h1>Кабель текущий</h1><div class="e-product-info product_card"><form id="cart-form"><div id="product-cart" data-id="42">'+offers+stocks+'<span class="e-product-prices__old" data-price="90000">90000 Р</span></div></form><div class="e-products-card__item"><span class="e-products-card__price">999 Р</span><meta itemprop="price" content="999"></div></div><script type="application/ld+json">'+json.dumps({'@type':'Product','name':'Кабель текущий','offers':{'price':77777,'priceCurrency':'RUB'}})+'</script></main>'
 def offer(amount,id,variant=''):
  return '<div itemprop="offers" itemscope itemtype="http://schema.org/Offer"><span itemprop="name">'+variant+'</span><meta itemprop="price" content="'+str(amount)+'"><meta itemprop="priceCurrency" content="RUB"><input name="sku_id" value="'+str(id)+'"></div>'
 stocks='<div class="sku-11-stock"><span class="stocks_block"><span class="stocks_title">Москва:</span><span class="e-product-stock">В наличии</span></span><span class="stocks_block"><span class="stocks_title">Петербург:</span><span class="e-product-stock">Под заказ</span></span></div>'
 result=c.details(src,record,page(offer(36900,11),stocks));assert [p['amount'] for p in result['prices']]==['36900.00'];assert result['prices'][0]['currency']=='RUB';assert result['availability']=='Москва: В наличии; Петербург: Под заказ';assert result['priceParser']==c.LANSET_PARSER
 variants=c.details(src,record,page(offer(7.2,11,'G652D')+offer(8.1,12,'G657A1'),stocks));assert [p['label'] for p in variants['prices']]==['Исполнение: G652D','Исполнение: G657A1'];assert variants['prices'][0]['availability'].startswith('Москва:');assert variants['prices'][1]['availability']==''
 assert c.details(src,record,page(offer(0,11)))['prices']==[]
 assert c.details(src,record,page(''))['prices']==[]
 try:c.details(src,{**record,'name':'Другой товар'},page(offer(1,11)))
 except ValueError:pass
 else:raise AssertionError('Wrong product accepted')
 legacy={**record,'prices':[c.price('Чужая цена','999 Р')],'availability':'В наличии'};legacy.pop('priceParser',None)
 c.save(legacy)
 with c.crm_store.connect() as db:
  saved=json.loads(db.execute('SELECT payload FROM competitor_products WHERE id=?',(record['id'],)).fetchone()[0]);assert saved['prices']==[]
  # Simulate a pre-upgrade database and verify reversible history quarantine.
  db.execute('UPDATE competitor_products SET payload=?,has_price=1 WHERE id=?',(json.dumps(legacy),record['id']))
  db.execute('DELETE FROM competitor_migrations WHERE id=?',(c.LANSET_PARSER,))
 c.init()
 with c.crm_store.connect() as db:
  assert json.loads(db.execute('SELECT payload FROM competitor_products WHERE id=?',(record['id'],)).fetchone()[0])['prices']==[]
  assert db.execute('SELECT count(*) FROM competitor_price_history WHERE product_id=?',(record['id'],)).fetchone()[0]==0
  assert db.execute('SELECT count(*) FROM competitor_price_quarantine WHERE product_id=?',(record['id'],)).fetchone()[0]>=1
 assert c.category('ОКПД-08А-(2,0)-2/4,6 (2кН) (8 волокон)','Для подвеса')=='Оптический кабель'
 assert c.category('Зажим для кабеля 8 волокон')=='Арматура и крепёж'
 assert c.category('COVLINE ADSS Flat Drop, 4 волокна','Для подвеса')=='Оптический кабель'
 c.save(result)
 with c.crm_store.connect() as db:assert db.execute('SELECT count(*) FROM competitor_price_history WHERE product_id=?',(record['id'],)).fetchone()[0]==1
 print('PASS Lanset: current product only, no recommendations/old prices/JSON-LD fallback, exact heading, variant SKU prices and stock, no zero prices, reversible legacy quarantine')
