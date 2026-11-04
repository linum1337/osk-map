"""Persistent company-map visibility and city centres, separate from source assets."""
import json,re
from pathlib import Path
import crm_store

def initialize():
 root=Path(__file__).resolve().parent/'app';scope=set();centres={}
 for name in ('scope-data.js','scope.js'):
  p=root/name
  if p.is_file():
   match=re.search(r'VISIBLE_OFFICE_IDS\s*=\s*new Set\((\[[\s\S]*?\])\)',p.read_text())
   if match:scope.update(json.loads(match[1]))
 p=root/'city-centres.js'
 if p.is_file():
  match=re.search(r'window.CITY_CENTRES\s*=\s*([\s\S]*?);?\s*$',p.read_text())
  if match:
   try:centres=json.loads(match[1].rstrip(';'))
   except ValueError:pass
 with crm_store.connect() as c:
  c.execute('CREATE TABLE IF NOT EXISTS workspace_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
  # A source-only deployment may have no private whitelist; geography still applies.
  for key,value in [('visibleIds',sorted(scope) if scope else None),('cityCentres',centres)]:c.execute('INSERT OR IGNORE INTO workspace_settings VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
def setting(key,default):
 with crm_store.connect() as c:row=c.execute('SELECT value FROM workspace_settings WHERE key=?',(key,)).fetchone()
 return json.loads(row[0]) if row else default
SCOPE_SCRIPT=r'''
window.inWorkArea=r=>{
 if(r.hiddenReason)return false;
 if(window.VISIBLE_OFFICE_IDS&&!window.VISIBLE_OFFICE_IDS.has(r.officeId))return false;
 const p=(window.CITY_CENTRES||{})[r.officeId]||{},region=[r.region,p.region].filter(Boolean).join(' ');
 if(/дагестан|кабардино[\s-]*балкар|чеч|ростов|ингуш/i.test(region))return false;
 if(/санкт[\s-]*петербург|спб/i.test(r.city||''))return false;
 if(/убрать|не\s*работа|не\s*действ|не\s*существ|закрыт|ликвидир/i.test(r.name||''))return false;
 const name=r.name||'';
 if(/ростелеком|мегафон|билайн|транстелеком|нетбайнет|вайфаер|wifire|простор\s*телеком/i.test(name)||/(^|[^а-яa-z0-9])(мтс|ттк|мгтс|t2|tele2)(?=$|[^а-яa-z0-9])/i.test(name))return false;
 if(/дом[.\s]?ру/i.test(name)&&!/ринет/i.test(name))return false;
 if(/ДАГЕСТАНСКАЯ ЭНЕРГЕТИЧЕСКАЯ КОМПАНИЯ/i.test(name)&&r.region==='Требует уточнения')return false;
 const lon=r.lon??p.lon;return r.city==='Екатеринбург'||lon==null||lon<=60.6;
};
'''
def scope_script():
 ids=setting('visibleIds',None)
 return ('window.VISIBLE_OFFICE_IDS=new Set('+json.dumps(ids)+');\n' if ids is not None else 'window.VISIBLE_OFFICE_IDS=null;\n')+SCOPE_SCRIPT
