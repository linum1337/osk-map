"""Closure sources, assets, variant capacities and default user isolation."""
import json,os,sys,tempfile,base64
from pathlib import Path
from urllib.parse import urlsplit
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='closure-fixture-password')
 import server
 c=server.app.test_client()
 def auth(login):return {'Authorization':'Basic '+base64.b64encode((login+':closure-fixture-password').encode()).decode(),'X-Requested-With':'OSK-Map'}
 assert c.post('/api/admin/accounts',headers=auth('admin'),json={'login':'Closure manager','role':'manager','password':'closure-fixture-password'}).status_code==201
 data=json.loads((root/'app/references/closures/closures.json').read_text());es=data['entries'];assert len(es)>=200 and len({e['id'] for e in es})==len(es)
 assert {'Volsip','ССД','Компонент','НАГ','Fibertool'}=={e['supplier'] for e in es}
 for e in es:
  assert e['fields'] and e['evidence']['source']==e['url'] and urlsplit(e['url']).scheme=='https'
  if e.get('image'):
   image=e['image'];assert image['reviewed'] and image['src'].startswith('/references/closures/images/')
   raw=(root/'app'/image['src'].lstrip('/')).read_text();assert '<svg' in raw and 'data:image/webp;base64,' in raw
 a=next(e for e in es if e['id']=='f8060ca86c39e99a');assert a['fields']['capacity']=='216' and a['fields']['cassettesIncluded']=='1'
 assert sum(e['supplier']=='Volsip' for e in es)>=60
 assert all(e.get('image') and e['image'].get('reviewed') for e in es)
 assert all('no-photo' not in e['image']['source'] for e in es)
 assert not any('склад' in k.casefold() for e in es for k,v in e['evidence']['propertyRows'])
 first=next(e['image']['src'] for e in es if e.get('image'))
 for path in ['/references/closures/closures.json','/references/closures/closures.js','/references/closures/analogs.js','/references/closures/closures.css',first]:
  assert c.get(path).status_code==401,path
  for prefix in ['', '/companies']:
   for method in ['get','head']:
    assert getattr(c,method)(prefix+path,headers=auth('Closure manager')).status_code==403,path
    r=getattr(c,method)(prefix+path,headers=auth('admin'));assert r.status_code==200 and 'no-store' in r.headers['Cache-Control'],path
 print('PASS closures: direct product sources, exact kit versus maximum capacity, Volsip variants, local reviewed images, default admin-only GET/HEAD and alias isolation')
