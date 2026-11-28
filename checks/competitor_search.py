"""Broad search must keep category isolation, rank exact SKUs, and expose safe ranges."""
import os,sys,tempfile,json,base64,time
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='search-fixture-password')
 import server,competitor_catalog as c,competitor_search as search
 client=server.app.test_client();headers={'Authorization':'Basic '+base64.b64encode(b'admin:search-fixture-password').decode()}
 def add(name,sku,properties,description='',provider='nk',category_path=''):
  p=c.make(c.BY_SOURCE[provider],c.BY_SOURCE[provider]['url']+'fixture-'+sku,name,category_path=category_path)
  p.update(sku=sku,properties=properties,description=description,manufacturer='Ёлка',availability='Под заказ')
  c.save(p);return p['id']
 exact=add('Муфта МТОК-Г3, 48 ОВ','130103-00905',{'Емкость':'48 волокон','Кассеты':'До четырёх кассет','Оболочка':'Полиэтилен'})
 other=add('Муфта МТОК-Г3, 96 ОВ','130103-00906',{'Емкость':'96 волокон'})
 add('Кронштейн крепления МТОК','XX-130103-00905',{'Материал':'Сталь'},description='Для муфты Г3')
 dangerous=add('Кабель тестовый','SAFE-1',{'Описание':'<img src=x onerror=alert(1)>'})
 def find(q,category=''):
  r=client.get('/competitors/api/products',query_string={'q':q,'category':category},headers=headers);assert r.status_code==200,r.data
  return r.json['products']
 for q in ['МУФТА мток 48','48 МТОК кассетой','МTОК-Г3 48','130103 00905','00905','13010300905','ЁЛКА 48','елка 48','48 волокно']:
  assert exact in [p['id'] for p in find(q)],q
 assert find('130103-00905')[0]['id']==exact,'exact SKU must rank before embedded reference'
 assert other not in [p['id'] for p in find('48 волокон')]
 assert exact not in [p['id'] for p in find('МТОК','Арматура и крепёж')]
 assert exact in [p['id'] for p in find('МТОК','Муфты')]
 assert not find('%_')
 for item in find("' OR 1=1 --"):
  body=search.document(item,c.BY_SOURCE[item['provider']]['name'])[0]
  assert all(word in body for word in search.terms("' OR 1=1 --"))
 rows=find('кассетой');p=next(p for p in rows if p['id']==exact);hit=next(h for h in p['searchMatches'] if h['key']=='property:Кассеты')
 assert any('кассет' in hit['text'][a:b].lower() for a,b in hit['ranges'])
 p=next(p for p in find('волокон 48') if p['id']==exact)
 assert any(h['key']=='name' and any(h['text'][a:b]=='ОВ' for a,b in h['ranges']) for h in p['searchMatches'])
 assert dangerous in [p['id'] for p in find('onerror')]
 p=next(p for p in find('onerror') if p['id']==dangerous);assert '<img' in next(h['text'] for h in p['searchMatches'] if h['key'].startswith('property:'))
 with c.crm_store.connect() as db:db.execute('DELETE FROM competitor_search WHERE id=?',(exact,));db.execute("DELETE FROM competitor_migrations WHERE id='search-v2'")
 c.init();assert exact in [p['id'] for p in find('МТОК 48')],'migration must rebuild existing catalogue'
 # Updating a product must replace its search document, removing stale matches.
 p=client.get('/competitors/api/product/'+exact,headers=headers).json['product'];p['properties'].pop('Кассеты');p['properties']['Лотки']='Не указано';p['detailCheckedAt']=c.now();c.save(p)
 assert exact not in [p['id'] for p in find('кассетой')]
 assert len(search.ranges('Муфта 130103-00905',search.terms('муфта 13010300905')))==2
 print('PASS search: Russian case/ё/endings, mixed alphabet markings, word order, mid-SKU fragments, characteristics, exact-SKU ranking, category isolation, literal queries, highlight offsets and updated/backfilled documents')
