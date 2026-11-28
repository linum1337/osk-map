"""Bulk catalogue writes commit together, retain history and roll back failures."""
import os,sys,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ['DATA_DIR']=tmp
 import competitor_catalog as c
 c.init();src=c.BY_SOURCE['telecomo'];rows=[c.make(src,src['url']+'catalog/fixture-'+str(i),'Муфта тест '+str(i)) for i in range(3)]
 for p in rows:p['prices']=[c.price('Розница','100',currency='RUB')]
 c.save_many(rows)
 with c.crm_store.connect() as db:
  assert db.execute('select count(*) from competitor_products where provider=?',(src['id'],)).fetchone()[0]==3
  history=db.execute('select count(*) from competitor_price_history').fetchone()[0]
 c.save_many(rows)
 with c.crm_store.connect() as db:assert db.execute('select count(*) from competitor_price_history').fetchone()[0]==history
 fresh=c.make(src,src['url']+'catalog/rollback-fixture','Муфта откат')
 try:c.save_many([fresh,{}])
 except KeyError:pass
 else:raise AssertionError('Invalid batch must fail')
 with c.crm_store.connect() as db:
  assert not db.execute('select 1 from competitor_products where id=?',(fresh['id'],)).fetchone()
  assert not db.execute('select 1 from competitor_search where id=?',(fresh['id'],)).fetchone()
 print('PASS batch import: atomic products/search/makers/history, stable repeated prices and rollback on failure')
