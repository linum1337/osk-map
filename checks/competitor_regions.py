"""Regional directory and product filters, federal scope and source boundaries."""
import os,sys,tempfile,json,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='region-fixture-only')
 import server,competitor_catalog as c
 from competitor_sources_extended import scope_allowed,listing
 client=server.app.test_client();auth={'Authorization':'Basic '+base64.b64encode(b'admin:region-fixture-only').decode()}
 assert len(c.SOURCES)==33 and len({s['id'] for s in c.SOURCES})==33
 assert len([s for s in c.SOURCES if 'anlan.ru' in s['url']])==1
 for id in ['component','sparta','etm','fibertool','linesv','bazis']:assert c.PRESENCE[id]['verified']
 assert c.source_in_region('etm','Краснодарский край') and c.source_in_region('etm','federal')
 assert not c.source_in_region('sparta','Ростовская область'),'Shipping cities are not offices'
 assert c.source_in_region('sparta','Нижегородская область')
 assert c.source_in_region('skeo','Ростовская область'),'Explicit regional sales group'
 for id in ['etm','linesv','sparta']:
  src=c.BY_SOURCE[id];url=src['url']+('cat/nn/9999999' if id=='etm' else 'fixture-network-product')
  p=c.make(src,url,'РегионФикстура Муфта');p['sourceCategoryUrl']=src['seeds'][0];c.save(p)
 def find(**params):return client.get('/competitors/api/products',query_string=params,headers=auth).json
 result=find(q='РегионФикстура',region='Краснодарский край');assert {p['provider'] for p in result['products']}=={'etm','linesv'}
 assert {p['provider'] for p in find(q='РегионФикстура',region='federal')['products']}=={'etm'}
 assert not find(q='РегионФикстура',region='Краснодарский край',provider='sparta')['products']
 assert {p['provider'] for p in find(q='РегионФикстура',region='Нижегородская область',category='Муфты')['products']}=={'etm','sparta'}
 assert not find(q='РегионФикстура',region='not-a-real-region')['products'] or all(p['provider']=='etm' for p in find(q='РегионФикстура',region='not-a-real-region')['products'])
 assert any(s['presence']['federal'] for s in result['sources']) and result['regions']
 etm=c.BY_SOURCE['etm'];assert scope_allowed(etm,etm['seeds'][0]) and scope_allowed(etm,'https://www.etm.ru/catalog/952510_opticheskie_kabeli')
 assert not scope_allowed(etm,'https://www.etm.ru/catalog/010_elektrotehnika') and not scope_allowed(etm,'https://www.etm.ru/catalog/9999_other')
 wrong=c.make(etm,'https://www.etm.ru/cat/nn/123','Товар вне раздела');wrong['prices']=[];wrong['sourceCategoryUrl']='https://www.etm.ru/catalog/010_other'
 r=client.post('/competitors/api/import',json={'products':[wrong]},headers=auth|{'X-Requested-With':'OSK-Map'});assert r.status_code==400
 html='<h1>Муфты</h1><div class="catalog-card"><a class="catalog-card__name" href="/catalog/test/">Муфта тест</a><div class="catalog-card__price">100 ₽</div></div><div class="recommendations"><div class="catalog-card"><a class="catalog-card__name" href="/catalog/other/">Муфта чужая</a><div class="catalog-card__price">99999 ₽</div></div></div>'
 ps,_=listing(c.BY_SOURCE['telecomo'],'https://telecomo.ru/catalog/',html);assert len(ps)==1 and ps[0]['prices'][0]['amount']=='100.00'
 try:listing(c.BY_SOURCE['anlan'],'https://anlan.ru/catalog','<h1>Подтвердите, что вы человек</h1>')
 except PermissionError:pass
 else:raise AssertionError('Challenge must not be treated as an empty successful catalogue')
 print('PASS regions: 33 suppliers, deduplication, physical vs shipping coverage, federal/local intersection, category/source filters, ETM scope enforcement, card-only prices and challenge detection')
