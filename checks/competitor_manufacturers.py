"""Manufacturers, brands, exact official URLs, and source/category filter composition."""
import os,sys,tempfile,base64,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
import competitor_manufacturers as m
from bs4 import BeautifulSoup
p={'name':'Муфта МТОК ССД 130103-01151','sku':'130103-01151','provider':'nk','url':'https://nk-groupltd.ru/shop/test/','properties':{}}
e=m.enrich(p);assert e['manufacturerKey']=='ssd' and e['manufacturerProductUrl'].startswith('https://ssd.ru/product/') and '130103_01151' in e['manufacturerProductUrl'];assert not e.get('originCountry')
unknown=m.enrich({**p,'name':'Муфта МТОК','sku':''});assert unknown['manufacturerKey']=='unknown' and not unknown['manufacturerProductUrl'],'Do not guess maker from generic model'
brand=m.enrich({**p,'name':'Муфта SNR-FOSC-8','sku':'','provider':'nag','url':'https://shop.nag.ru/product/test','manufacturer':'SNR'});assert brand['brand']=='SNR' and not brand['manufacturer'] and brand['brandProductUrl']==brand['url'];assert not brand.get('originCountry')
country=m.enrich({**p,'name':'Кабель','sku':'','properties':{'Производитель':'Китай'}});assert country['originCountry']=='Китай' and not country['manufacturer'] and country['manufacturerKey']=='unknown'
notcountry=m.enrich({**p,'name':'Кабель','sku':'','manufacturerDeclaration':'Инкаб'});assert notcountry['manufacturerKey']=='incab' and not notcountry.get('originCountry')
noisy=m.enrich({**p,'name':'Компрессор','sku':'','properties':{'Производительность м³/час':'Китай'}});assert not noisy.get('originCountry') and noisy['manufacturerKey']=='unknown'
html='<div class="e-product-info product_card"><table class="e-product-features__table"><tr><td>Производитель</td><td>ССД</td></tr><tr><td>Бренд</td><td>ССД</td></tr></table></div><div itemscope itemtype="http://schema.org/Product"><h1>Другой товар</h1><span itemprop="manufacturer">Чужой завод</span></div>'
claim=m.read_claims({**p,'provider':'lanset'},BeautifulSoup(html,'html.parser'));assert claim['manufacturerDeclaration']=='ССД' and claim['brandDeclaration']=='ССД'
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='maker-fixture-password')
 import server,competitor_catalog as c
 client=server.app.test_client();headers={'Authorization':'Basic '+base64.b64encode(b'admin:maker-fixture-password').decode()}
 ids=[]
 for provider in ['nk','install']:
  record=c.make(c.BY_SOURCE[provider],c.BY_SOURCE[provider]['url']+'maker-fixture','MakerFixture Муфта ССД 130103-01151');record.update(sku='130103-01151',detailCheckedAt=c.now(),manufacturerDeclaration='ССД')
  c.save(record);ids.append(record['id'])
 def find(**query):
  r=client.get('/competitors/api/products',query_string=query,headers=headers);assert r.status_code==200,r.data;return r.json
 result=find(q='MakerFixture',manufacturer='ssd',category='Муфты');assert {p['id'] for p in result['products']}==set(ids)
 assert {p['provider'] for p in result['products']}=={'nk','install'}
 assert {p['id'] for p in find(q='MakerFixture',manufacturer='ssd',provider='nk')['products']}=={ids[0]}
 assert not find(q='MakerFixture',manufacturer='incab')['products']
 assert not find(q='MakerFixture',manufacturer='ssd',category='Оптический кабель')['products']
 assert any(x['id']=='ssd' for x in result['manufacturers'])
 with c.crm_store.connect() as db:before=db.execute('SELECT count(*) FROM competitor_price_history WHERE product_id=?',(ids[0],)).fetchone()[0]
 current=client.get('/competitors/api/product/'+ids[0],headers=headers).json['product'];c.save(current)
 with c.crm_store.connect() as db:assert db.execute('SELECT count(*) FROM competitor_price_history WHERE product_id=?',(ids[0],)).fetchone()[0]==before
 assert client.post('/competitors/api/manufacturers',headers={**headers,'X-Requested-With':'OSK-Map','Origin':'https://other.invalid'},json={'items':[]}).status_code==403
 before_record=client.get('/competitors/api/product/'+ids[0],headers=headers).json
 response=client.post('/competitors/api/manufacturers',headers={**headers,'X-Requested-With':'OSK-Map'},json={'items':[{'id':ids[0],'brandDeclaration':'SSD MetaFixture'}]});assert response.status_code==200,response.data
 after_record=client.get('/competitors/api/product/'+ids[0],headers=headers).json
 assert after_record['product']['prices']==before_record['product']['prices'] and after_record['history']==before_record['history']
 assert after_record['product']['brandDeclaration']=='SSD MetaFixture'
print('PASS manufacturers: exact official article links, brand/factory separation, no guessed country/maker, scoped source claims, maker+supplier+category filters, unchanged price history')
