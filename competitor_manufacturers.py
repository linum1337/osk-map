"""Declared manufacturers/brands and verified product links, never inferred origin."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DATA=json.loads((ROOT/'app/competitors/manufacturer-links.json').read_text())
MAKERS={m['id']:m for m in DATA['manufacturers']}
_VERSION='manufacturer-v1'
def norm(text):return re.sub(r'[^a-zа-я0-9]','',str(text).casefold().replace('ё','е'))
_ALIASES={}
for maker in MAKERS.values():
 for alias in [maker['name'],*maker.get('aliases',[])]:_ALIASES[norm(alias)]=maker['id']
_ALIASES.update({norm(k):v for k,v in {'МКФ':'mkf','МКЗ Минсккабель':'minsk','Интегра Кабель':'integra','СОЮЗ-КАБЕЛЬ':'integra','СОКК':'socc','СаранскКабель':'sarko','СаранскКабель-Оптика':'sarko','Еврокабель-1':'euro','Старлинк':'starlink','ССД':'ssd','ОСК':'osk'}.items()})
_BRAND_ONLY={norm(x) for x in ['COVLINE','SNR','NTSS','СКО','NETLAN','REXANT','NIKOLAN','NIKOMAX','PROconnect','IT.Rex','Cabeus','Hyperline','LANSET','ОСК','Volsip']}
_COUNTRIES={'китай':'Китай','кнр':'Китай','china':'Китай','россия':'Россия','рф':'Россия','беларусь':'Беларусь','республикабеларусь':'Беларусь'}
# A short brand is recognised only as a separate word, never from an ambiguous cable code.
_SHORT=[('ssd',re.compile(r'(?<![а-яa-z0-9])ССД(?![а-яa-z0-9])',re.I)),('snr',re.compile(r'(?<![a-z0-9])SNR(?![a-z0-9])',re.I))]
def resolve(value):return _ALIASES.get(norm(value),'')
def declaration(out,key,value):
 value=str(value or '').strip()
 if not value:return
 key=re.sub(r'[:\s]+',' ',str(key).strip().casefold()).strip()
 if key in ['производитель','изготовитель','завод изготовитель','завод-изготовитель']:
  country=_COUNTRIES.get(norm(value))
  if country:out.update(originCountry=country,originEvidence='supplier-card')
  else:out['manufacturerDeclaration']=value
 elif key in ['бренд','торговая марка','марка производителя']:out['brandDeclaration']=value
 elif key in ['страна производства','страна происхождения','страна изготовитель','страна-изготовитель']:
  out.update(originCountry=_COUNTRIES.get(norm(value),value),originEvidence='supplier-card')

def read_claims(record,soup):
 out=dict(record);provider=record['provider'];roots=[]
 if provider=='lanset':roots=soup.select('.e-product-info.product_card .e-product-features__table')
 elif provider=='nk':roots=soup.select('#tab-additional_information, .woocommerce-product-attributes')
 elif provider=='nag':roots=soup.select('[itemprop="additionalProperty"]')
 elif provider=='osk':roots=soup.select('.main-section-block')
 elif provider=='install':roots=soup.select('.props_list, .item_main_info, .props_list__table')
 elif provider=='yotta':roots=soup.select('article.node-product')
 elif provider=='pkk':roots=soup.select('.product-page')
 else:roots=soup.select('[itemprop="additionalProperty"]')
 for root in roots:
  rows=[root] if root.get('itemprop')=='additionalProperty' else root.select('tr')
  for row in rows:
   cells=[row.select_one('[itemprop="name"]'),row.select_one('[itemprop="value"]')] if row.get('itemprop')=='additionalProperty' else row.find_all(['th','td'],recursive=False)
   if len(cells)==2 and all(cells):declaration(out,*(e.get_text(' ',strip=True) for e in cells))
 if provider=='yotta':
  for root in roots:
   for label in root.select('.field-label'):
    parent=label.parent;value=parent.select_one('.field-items')
    if value:declaration(out,label.get_text(' ',strip=True),value.get_text(' ',strip=True))
 # Schema manufacturer and brand are separate concepts.
 for key in ['manufacturer','brand']:
  for node in soup.select('[itemprop="'+key+'"]'):
   # Skip widgets/recommendations whose own Product differs from the page title.
   owner=node.find_parent(attrs={'itemtype':re.compile(r'/Product$')})
   heading=(owner.select_one('h1') or owner.select_one('[itemprop="name"]')) if owner else None
   if heading is None or norm(heading.get('content') or heading.get_text(' ',strip=True))!=norm(record.get('name','')):continue
   value=node.get('content') or node.get_text(' ',strip=True)
   if value and len(value)<150:
    out['manufacturerDeclaration' if key=='manufacturer' else 'brandDeclaration']=value;break
 return out

def manufacturer_link(record,key):
 # Exact manufacturer articles have priority over series-name matching.
 articles=[]
 for value in [record.get('sku',''),record.get('name','')]:
  articles+=re.findall(r'(?<!\d)\d{6}-\d{5}(?!\d)',str(value))
 urls={DATA['ssdArticles'][a] for a in articles if a in DATA['ssdArticles']}
 if len(urls)==1 and (not key or key=='ssd'):return 'ssd',next(iter(urls)),'product'
 if not key:return '', '', ''
 title=norm(record.get('name',''));candidates={}
 for entry in DATA['entries']:
  if entry['maker']!=key:continue
  for mark in re.split(r',\s+(?=[А-ЯA-Zа-яa-z])|;',entry['mark']):
   code=norm(mark)
   if len(code)>=3 and code in title:candidates[entry['url']]=entry['kind']
 if len(candidates)==1:
  url=next(iter(candidates));return key,url,candidates[url]
 return key,'',''

def enrich(record):
 out={**record}
 if out.get('manufacturerVersion')!=_VERSION:
  # Earlier JSON-LD imports combined brand with manufacturer: retain it as a brand.
  if out.get('manufacturer') and not out.get('manufacturerDeclaration'):
   out.setdefault('brandDeclaration',out['manufacturer']);out.setdefault('manufacturerPrevious',out['manufacturer'])
  out['manufacturer']=''
 for key,value in (out.get('properties') or {}).items():declaration(out,key,value)
 raw=out.get('manufacturerDeclaration','');brand=out.get('brandDeclaration',out.get('brand',''))
 if norm(raw) in _COUNTRIES:
  out.update(originCountry=_COUNTRIES[norm(raw)],originEvidence='supplier-card');raw='';out.pop('manufacturerDeclaration',None)
 if brand:out['brand']=brand
 maker=resolve(raw) or resolve(brand)
 evidence='supplier-card' if raw or brand else ''
 if not maker:
  # Only an explicit factory/brand name in the product title/category is used.
  label=str(out.get('name',''))+' '+str(out.get('categoryPath',''))
  for alias,key in _ALIASES.items():
   if len(alias)<4:continue
   if alias in norm(label):
    # Require the complete declared alias, not a short cable family code.
    original=next((a for a in [MAKERS[key]['name'],*MAKERS[key].get('aliases',[])] if norm(a)==alias),'')
    if original and re.search(r'(?<![а-яa-z0-9])'+re.escape(original)+r'(?![а-яa-z0-9])',label,re.I):maker=key;break
  if not maker:
   for key,pattern in _SHORT:
    if pattern.search(label):maker=key;break
  if maker:evidence='supplier-title'
 if out.get('provider')=='osk' and '/kabel-osk/' in out.get('url',''):maker='osk';brand='ОСК';evidence='supplier-category'
 key,url,kind=manufacturer_link(out,maker)
 if key=='ssd' and url:
  maker=key;raw=MAKERS[key]['name'];out['manufacturerDeclaration']=raw;evidence='official-article'
 out['manufacturerProductUrl']='';out['brandProductUrl']='';out['manufacturerLinkKind']='';out['brandLinkKind']=''
 if maker:
  m=MAKERS[maker];label=m['name']
  is_brand=m.get('brandOnly') or norm(raw or brand or label) in _BRAND_ONLY or maker=='osk'
  if is_brand:
   out['brand']=brand or raw or label;out['manufacturer']=''
   if url:out.update(brandProductUrl=url,brandLinkKind=kind)
  else:
   out['manufacturer']=label
   if url:out.update(manufacturerProductUrl=url,manufacturerLinkKind=kind)
  out.update(manufacturerKey=maker,manufacturerLabel=label+(' (бренд)' if is_brand else ''),manufacturerEvidence=evidence)
 else:
  if raw and norm(raw) not in _BRAND_ONLY:out['manufacturer']=raw;label=raw;key='declared:'+norm(raw)
  else:
   if not brand and raw:brand=raw
   # Explicit private labels in the supplier title remain brands, not named factories.
   if not brand:
    for value in ['COVLINE','NTSS','NETLAN','REXANT','NIKOLAN','NIKOMAX','PROconnect','Hyperline','Cabeus','LANSET']:
     if re.search(r'(?<![a-zа-я0-9])'+re.escape(value)+r'(?![a-zа-я0-9])',str(out.get('name','')),re.I):brand=value;break
   out['brand']=brand;label=(brand+' (бренд)') if brand else 'Не указан';key='brand:'+norm(brand) if brand else 'unknown'
  out.update(manufacturerKey=key,manufacturerLabel=label,manufacturerEvidence=evidence)
 if out.get('brand') and out.get('provider')=='nag' and resolve(out['brand'])=='snr':out.update(brandProductUrl=out['url'],brandLinkKind='product')
 if maker=='osk' and out.get('provider')=='osk' and '/kabel-osk/' in out.get('url',''):out.update(brandProductUrl=out['url'],brandLinkKind='family')
 out['manufacturerVersion']=_VERSION
 return out
