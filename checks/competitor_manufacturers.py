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
 # Rebuild legacy manufacturer/search indexes without recording a price change.
 legacy=c.make(c.BY_SOURCE['nk'],c.BY_SOURCE['nk']['url']+'legacy-cable','Кабель ОККМС-0,22-48')
 legacy.update(manufacturerVersion='manufacturer-v1',manufacturerKey='unknown',manufacturerLabel='Не указан',prices=[{'amount':'25.00','currency':'RUB','label':'Цена'}])
 with c.crm_store.connect() as db:
  db.execute('INSERT OR REPLACE INTO competitor_products VALUES(?,?,?,?,?,?,?,?)',(legacy['id'],'nk','Оптический кабель',legacy['name'],'',json.dumps(legacy),1,legacy['checkedAt']))
  db.execute("DELETE FROM competitor_migrations WHERE id='manufacturer-v2'")
  before_all=db.execute('SELECT count(*) FROM competitor_price_history').fetchone()[0]
 c.init()
 upgraded=client.get('/competitors/api/product/'+legacy['id'],headers=headers).json['product']
 assert upgraded['manufacturerKey']=='sarko' and upgraded['prices']==legacy['prices'] and upgraded['checkedAt']==legacy['checkedAt']
 assert legacy['id'] in [p['id'] for p in find(q='ОККМС',manufacturer='sarko')['products']]
 with c.crm_store.connect() as db:assert db.execute('SELECT count(*) FROM competitor_price_history').fetchone()[0]==before_all
print('PASS manufacturers: exact official article links, brand/factory separation, no guessed country/maker, scoped source claims, maker+supplier+category filters, unchanged price history')

def cable(name,**extra):return m.enrich(dict(name=name,category='Оптический кабель',provider='optikkom',url='https://www.optik-kom.ru/goods/test',properties={},prices=[])|extra)
for mark,key,path in [('ОККМС-0,22-48 7кН','sarko','/okkms/'),('ОККС-0,22-48','sarko','/okks/'),('ОКПК-0,22-4','sarko','/okpk/'),('ОКМС-16 10кН','transvoc','item=3'),('ОМЗКГЦ-10-01-0,22-8','beltele','odnomodulnoj'),('ОКНГ (В/Т2)','altay','okng-vt2')]:
 e=cable('Кабель '+mark);assert e['manufacturerKey']==key and path in e['manufacturerProductUrl'],e;assert e['manufacturerEvidence']=='reference-mark' and not e.get('originCountry');assert m.enrich(e)==e
for name in ['Кабель ОКБ-16 7кН','Кабель ОККМ-16','Кабель ДПО-16','Кабель ОКТм-16','Кабель ОККМСХ-16','Кабель ОКСЛ-М, ОКСТМ, ОКЛм','Кабель ОККМС / ОМЗКГЦ','Зажим для кабеля ОККМС']:
 assert cable(name)['manufacturerKey']=='unknown',name
assert cable('Кабель ОККМС',originCountry='Китай')['manufacturerKey']=='unknown'
assert cable('Кабель ОККМС',manufacturerDeclaration='Другой завод')['manufacturer']=='Другой завод'
e=cable('Кабель ОКМБ-02',prices=[{'label':'Исполнение: Кабель СЛ-ОКМБ 02НУ-4Е2-2,5','amount':'10.00'}]);assert e['manufacturerKey']=='starlink' and '/sl-okmb-02/' in e['manufacturerProductUrl']
e=cable('Кабель ОКМБ-02');assert e['manufacturerKey']=='unknown','Omitted factory prefix is ambiguous'
e=cable('Кабель СЛ-ОКПЦ-Д2к');assert e['manufacturerKey']=='starlink' and 'kruglyy' in e['manufacturerProductUrl']
assert cable('Кабель СЛ-ОКМБ-02 / ОККМС')['manufacturerKey']=='unknown','Conflicting factories'
print('PASS cable markings: reviewed complete families, variant markings, exact series links, no ambiguous parents/alternatives/country conflicts or declared-maker overrides')
