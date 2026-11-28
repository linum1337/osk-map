"""Public network-product catalogues and price tiers from the seven configured suppliers."""
import json,re,ssl,certifi,time,hashlib,threading,uuid,os,collections,contextlib
from pathlib import Path
from urllib.parse import urljoin,urlsplit,urlunsplit,parse_qsl,urlencode
from urllib.request import Request,build_opener,HTTPRedirectHandler,HTTPSHandler
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.error import HTTPError
from bs4 import BeautifulSoup
import crm_store
import competitor_search as search
import competitor_manufacturers as makers
from closure_prices import money,now,text,norm
LANSET_PARSER='lanset-product-offers-v2'
ROOT=Path(__file__).resolve().parent
SOURCES=json.loads((ROOT/'competitor_sources.json').read_text());BY_SOURCE={s['id']:s for s in SOURCES}
PRESENCE=json.loads((ROOT/'competitor_presence.json').read_text())
REGIONS=sorted(set(json.loads((ROOT/'competitor_regions.json').read_text()))|{r for p in PRESENCE.values() for r in p.get('regions',[])+p.get('salesRegions',[])})
def source_in_region(id,region):
 p=PRESENCE.get(id,{})
 return not region or (p.get('federal') if region=='federal' else not p.get('verified') if region=='unknown' else p.get('federal') or region in p.get('regions',[])+p.get('salesRegions',[]))
CATEGORIES=['Оптический кабель','Витая пара','Муфты','Кроссы и боксы','Арматура и крепёж','Пассивные компоненты','Сетевое оборудование','Инструмент и измерение','Шкафы и стойки','Колодцы и кабельная канализация','Прочие комплектующие']

def hostnames(src):
 host=urlsplit(src['url']).hostname;return {host,host.removeprefix('www.'),'www.'+host.removeprefix('www.')}
def safe_url(src,url):
 try:p=urlsplit(url);return p.scheme in ({'http','https'} if src['id']=='yotta' or src.get('allowHttp') else {'https'}) and p.hostname in hostnames(src) and not p.username and not p.password and p.port in (None,80 if p.scheme=='http' else 443)
 except ValueError:return False
def canonical(src,url):
 url=urljoin(src['url'],url);p=urlsplit(url)
 if not safe_url(src,url):return None
 query=[(k,v) for k,v in parse_qsl(p.query) if (k in ('page','PAGEN_1','PAGEN_2','start','limitstart') and v.isdigit() and 1<int(v)<100000) or (src['id']=='mircable' and k=='q' and len(v)<=500) or (src['id']=='kabis' and ((k=='view' and v=='product') or (k=='id' and v.isdigit())))]
 return urlunsplit((p.scheme,urlsplit(src['url']).netloc,p.path,urlencode(query),''))
class Redirect(HTTPRedirectHandler):
 def __init__(self,src):self.src=src
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if not safe_url(self.src,newurl):raise ValueError('Off-source redirect')
  return super().redirect_request(req,fp,code,msg,headers,newurl)
def fetch_bytes(src,url,with_charset=False):
 if not safe_url(src,url):raise ValueError('Unsupported source URL')
 context=ssl.create_default_context();context.load_verify_locations(cafile=certifi.where())
 req=Request(url,headers={'User-Agent':'OSK-Product-Reference/1.0 (+https://osk.l1num.ru/)','Accept':'text/html','Accept-Language':'ru,en;q=0.5'})
 with build_opener(Redirect(src),HTTPSHandler(context=context)).open(req,timeout=15) as r:
  raw=r.read(10_000_001)
  if len(raw)>10_000_000:raise ValueError('Response too large')
  return (raw,r.headers.get_content_charset() or 'utf-8') if with_charset else raw
def fetch(src,url):
 raw,charset=fetch_bytes(src,url,True);return raw.decode(charset,errors='replace')
def category(name,path=''):
 s=name.lower();matches=[]
 if re.match(r'^(?:оптическая\s+)?кабельная\s+сборка',s):return 'Пассивные компоненты'
 for value,pattern in [('Муфты',r'муфт|muft'),('Кроссы и боксы',r'кросс|бокс|крт|kross|box'),('Витая пара',r'витая|витой|utp|ftp|sftp|vitaya|mednye-kabeli'),('Оптический кабель',r'кабель.*оптич|оптич.*кабел|kabel.*optic|optic.*kabel|дроп.кабел|adss|flat.drop|(?:^|\s)(?:ок[а-я]{1,6}|о[тсцпд][а-я]{0,4})[-–\d]|\d+\s*(?:волокон|волокна|ов\b)'),('Арматура и крепёж',r'арматур|зажим|креплен|подвес|кронштейн|хомут|armatur|kreplen|podves'),('Инструмент и измерение',r'инструмент|измер|сварочн|рефлектом|стриппер|скалывател|instrument|izmer'),('Шкафы и стойки',r'шкаф|стойк|shkaf|stoyk'),('Колодцы и кабельная канализация',r'колод|люк|узк|труб|kolod|kanaliz'),('Сетевое оборудование',r'коммутатор|трансивер|роутер|медиаконверт|gpon|gepon|xpon|sfp|switch|wdm'),('Пассивные компоненты',r'патч|пигтейл|адаптер|разветв|аттенюат|розет|коннектор|кдзс|кассет|patch|pigt|splitter')]:
  match=re.search(pattern,s)
  if match:matches.append((match.start(),value))
 if matches:return min(matches,key=lambda v:v[0])[1]
 return category(path) if path and not re.search(r'монтаж|строительство',path,re.I) else 'Прочие комплектующие'
def product_id(src,url,source_id=''):return hashlib.sha256((src['id']+'|'+url+('|'+source_id if source_id else '')).encode()).hexdigest()[:20]
def price(label,raw,unit='',tax='',condition='',currency=''):
 value=money(raw)
 if not value:return None
 currency=currency or ('USD' if '$' in str(raw) else 'EUR' if '€' in str(raw) else 'RUB' if re.search(r'₽|руб|\bр\.?\b',str(raw),re.I) else '')
 if currency=='RUR':currency='RUB'
 if re.match(r'^\s*от\s',str(raw),re.I):condition='от '+value+(' · '+condition if condition else '')
 return {'label':label or 'Цена на странице','amount':value,'currency':currency,'unit':unit,'tax':tax,'condition':condition,'sourceText':str(raw)}
def unit_from(raw):
 m=re.search(r'(?:/|за\s+)(шт\.?|м(?:етр)?\.?|км|бухт\w*|компл\w*|упак\w*)',raw,re.I);return m[1] if m else ''
def prices_in(scope,source):
 if scope is None:return []
 result=[]
 def add(label,raw,**kwargs):
  p=price(label,raw,**kwargs)
  if p and p not in result:result.append(p)
 for group in scope.select('.price_group'):
  label=text(group.select_one('.price_name'))
  for block in group.select('.price_matrix_wrapper .price'):
   add(label,text(block.select_one('.price_value')) or block.get('data-value',''),currency=block.get('data-currency',''),unit=text(block.select_one('.price_measure')).lstrip('/'),condition=text(block.select_one('.price_interval')))
 if source=='nk':
  for block in scope.select('.price'):
   current=block.select_one('ins .amount') or block.select_one('.amount');raw=text(current)
   add('Опт' if 'ced_cwsm_price' in block.get('class',[]) else 'Цена на странице',raw,unit=unit_from(text(block)))
 if source=='nag':
  for block in scope.select('.our-price, .product-card-prices__price'):add('Цена на странице',text(block),unit=unit_from(text(block)))
 if source=='lanset':
  # Listing cards only. Product-page recommendations are never price sources.
  for block in scope.select('.e-products-card__price'):
   if block.find_parent(class_=lambda c:c and ('old' in c or 'compare' in c)):continue
   add('Цена на странице',text(block),unit=unit_from(text(block)))
 if source=='yotta':
  for block in scope.select('.views-field-field-price .field-content'):add('Цена на странице',text(block),unit=unit_from(text(block)))
 if source=='pkk':
  for block in scope.select('.price'):add('Цена на странице',text(block),unit=unit_from(text(block)))
 if source=='optikkom':
  for block in scope.select('[itemprop="price"], .price, .price__value'):add('Цена на странице',block.get('content') or text(block),unit=unit_from(text(block.parent)))
 return result

def lanset_stock(scope):
 if scope is None:return ''
 rows=[]
 for block in scope.select('.stocks_block'):
  city=text(block.select_one('.stocks_title'));value=text(block.select_one('.e-product-stock'))
  if value:rows.append((city+' '+value).strip())
 if rows:return '; '.join(dict.fromkeys(rows))
 value=text(scope.select_one('.e-products-card__stock, .e-product-stock'))
 if value:return value
 offer=scope.select_one('[itemprop="availability"]')
 return {'InStock':'В наличии','OutOfStock':'Нет в наличии','PreOrder':'Под заказ','BackOrder':'Под заказ','Discontinued':'Снят с производства'}.get((offer.get('href','').rsplit('/',1)[-1] if offer else ''),'')

def lanset_prices(form):
 result=[]
 for offer in form.select('[itemprop="offers"][itemtype$="/Offer"]'):
  amount=offer.select_one('[itemprop="price"]');currency=offer.select_one('[itemprop="priceCurrency"]')
  if amount is None or currency is None:continue
  # Each price belongs to its own SKU/Offer, not AggregateOffer or related cards.
  variant=text(offer.select_one('[itemprop="name"]'));sku=offer.select_one('input[name="sku_id"]')
  sku_id=sku.get('value','') if sku else '';sku_code=sku.get('data-sku-number','') if sku else ''
  stocks=form.select_one('.sku-'+sku_id+'-stock') if sku_id.isdigit() else None
  availability=lanset_stock(stocks if stocks is not None else offer)
  p=price('Исполнение: '+variant if variant else 'Цена на странице',amount.get('content') or text(amount),currency=currency.get('content') or text(currency))
  if not p:continue
  p.update(sku=sku_code,skuId=sku_id,availability=availability)
  if sku_code:p['condition']='Артикул: '+sku_code
  if p not in result:result.append(p)
 return result

def make(src,url,name,scope=None,category_path=''):
 url=canonical(src,url)
 if not url or not name.strip():return None
 sku=text(scope.select_one('.sku, .e-products-card__sku, .setout__article-sku, .article')) if scope else ''
 sku=re.sub(r'^(?:Артикул|Арт\.?|Код товара)\s*[:—-]?\s*','',sku,flags=re.I)
 return {'id':product_id(src,url),'provider':src['id'],'name':name.strip(),'sku':sku,'manufacturer':'','category':category(name,category_path),'categoryPath':category_path,'url':url,'properties':{},'prices':prices_in(scope,src['id']),'availability':text(scope.select_one('.availability, .e-products-card__stock, .setout__presence, .item-stock')) if scope else '', 'checkedAt':now(),'detailCheckedAt':None,**({'priceParser':LANSET_PARSER} if src['id']=='lanset' else {})}

def listing(src,url,html):
 if src.get('adapter')=='extended':
  from competitor_sources_extended import listing as extended_listing
  return extended_listing(src,url,html)
 if src['id']=='osk':
  from competitor_sources_extra import osk_listing
  return osk_listing(src,url,html)
 s=BeautifulSoup(html,'html.parser');sid=src['id'];products=[];links=[];title=text(s.select_one('h1'));scopes=[]
 if re.search(r'архив|arhiv|archive',title+' '+url,re.I):return [],[]
 if sid=='lanset':scopes=s.select('.e-products-card__item')
 elif sid=='install':scopes=s.select('.catalog_item')
 elif sid=='nk':scopes=s.select('li.product')
 elif sid=='nag':scopes=s.select('.setout__item, .product-item')
 elif sid=='yotta':scopes=s.select('.view-catalog-taxonomy.catalog-products .views-row')
 elif sid=='pkk':
  for a in s.select('a[href]'):
   if re.search(r'/catalog/[^?#]+/\d+/?$',a['href']) and a.select_one('.name'):scopes.append(a)
 elif sid=='optikkom':scopes=s.select('[itemtype*="Product"], li.product')
 for card in scopes:
  selectors={'lanset':'.e-products-card__link','install':'.item-title a, .js-notice-block__title','nk':'a.woocommerce-loop-product__link','nag':'.setout__name a','yotta':'.views-field-title a','pkk':'a[href]','optikkom':'a[href*="/goods/"]'}
  a=card if sid=='pkk' else card.select_one(selectors[sid])
  if not a:continue
  n=card.select_one('.e-products-card__name, .woocommerce-loop-product__title, .name, .setout__name a, .views-field-title a, .item-title a, .js-notice-block__title')
  name=text(n) or a.get('title') or text(a)
  p=make(src,urljoin(url,a.get('href','')),name,card,title)
  if p:products.append(p)
 # Follow actual category and pagination links only. Never manufacture page ranges.
 for a in s.select('a[href]'):
  href=canonical(src,urljoin(url,a['href']))
  if not href:continue
  path=urlsplit(href).path;parent=urlsplit(url).path.rstrip('/');page=bool(urlsplit(href).query)
  allowed=False
  if sid=='lanset':allowed=path.startswith('/category/') and any(path.startswith(urlsplit(seed).path) for seed in src['seeds'])
  elif sid=='install':allowed=path.startswith('/catalog/telekommunikatsionnye_seti_1/') and not re.search(r'/\d+/?$',path)
  elif sid=='nk':allowed=path.startswith('/product-category/') and 'elektronnye-komponenty' not in path
  elif sid=='pkk':allowed=path.startswith('/catalog/') and not re.search(r'/\d+/?$',path)
  elif sid=='yotta':allowed=path.startswith('/katalog-tovarov')
  elif sid=='nag':
   allowed=page and path==urlsplit(url).path
   # Category cards are scoped to the body, not the global mega-menu.
   if a.find_parent(class_=lambda c:c and ('Categories' in c or 'subcategory' in c.lower())) and path.startswith('/catalog/') and 'elektricheskij-kabel' not in path:allowed=True
  elif sid=='optikkom':allowed=path.startswith('/catalog')
  if allowed and not re.search(r'/arhiv|/archive',path,re.I):links.append(href)
 return products,list(dict.fromkeys(links))

def details(src,record,html):
 if src.get('adapter')=='extended':
  from competitor_sources_extended import details as extended_details
  return extended_details(src,record,html)
 if src['id']=='osk':
  from competitor_sources_extra import osk_details
  return osk_details(src,record,html)
 s=BeautifulSoup(html,'html.parser');sid=src['id'];scope=None
 if sid in ('install',):scope=s.select_one('.item_main_info')
 elif sid=='nk':scope=s.select_one('.summary.entry-summary')
 elif sid=='nag':scope=s.select_one('.product-card__prices')
 elif sid=='yotta':scope=s.select_one('article.node-product')
 elif sid=='pkk':scope=s.select_one('.product-page')
 elif sid=='lanset':scope=s.select_one('.e-product-info.product_card')
 elif sid=='optikkom':scope=s.select_one('[itemtype*="/Product"]') or s.select_one('.product')
 if scope is None:raise ValueError('Product scope missing')
 title=text(s.select_one('.zag > .wrap > span' if sid=='pkk' else 'h1'))
 if title and norm(title)!=norm(record['name']) and not(norm(title) in norm(record['name']) or norm(record['name']) in norm(title)):raise ValueError('Different product heading')
 out={**record,'detailCheckedAt':now(),'checkedAt':now()};out['prices']=prices_in(scope,sid)
 if sid=='lanset':
  if not title or norm(title)!=norm(record['name']):raise ValueError('Different Lanset product heading')
  form=scope.select_one('form#cart-form');cart=form.select_one('#product-cart[data-id]') if form else None
  if form is None or cart is None:raise ValueError('Lanset current-product form missing')
  out['prices']=lanset_prices(form);out['priceParser']=LANSET_PARSER
  stocks=[p['availability'] for p in out['prices'] if p.get('availability')]
  out['availability']=stocks[0] if stocks and len(set(stocks))==1 else ('Зависит от исполнения' if stocks else lanset_stock(form))
  main_sku=form.select_one('.e-product-sku')
  if main_sku:out['sku']=re.sub(r'^Артикул:\s*','',text(main_sku))
 if sid=='nag':
  from closure_prices import parse as nag_prices
  out['prices']=nag_prices({**record,'supplier':'НАГ'},html)
 # Product JSON-LD only when identity matches; never scrape recommendations as offers.
 for script in ([] if sid=='lanset' else s.select('script[type="application/ld+json"]')):
  try:payload=json.loads(script.string or script.get_text())
  except (ValueError,TypeError):continue
  stack=payload if isinstance(payload,list) else [payload]
  while stack:
   node=stack.pop()
   if not isinstance(node,dict):continue
   stack.extend(node.get('@graph',[]))
   if node.get('@type')!='Product' or norm(node.get('name'))!=norm(title or record['name']):continue
   if node.get('sku'):out['sku']=str(node['sku'])
   for field,target in [('manufacturer','manufacturerDeclaration'),('brand','brandDeclaration')]:
    value=node.get(field)
    if value:out[target]=value.get('name','') if isinstance(value,dict) else str(value)
   offers=node.get('offers',[]);offers=offers if isinstance(offers,list) else [offers]
   if not out['prices']:
    for offer in offers:
     if isinstance(offer,dict):
      p=price(offer.get('name','Цена на странице'),offer.get('price',''),unit=offer.get('unitText',''))
      if p:p['currency']=offer.get('priceCurrency','RUB');out['prices'].append(p)
 spec_root=s.select_one('#tab-additional_information') if sid=='nk' else scope
 if spec_root is None:spec_root=scope
 for tr in (s.select('[itemprop="additionalProperty"]') if sid=='nag' else spec_root.select('table tr, [itemprop="additionalProperty"]')):
  if tr.get('itemprop')=='additionalProperty':cells=[tr.select_one('[itemprop="name"]'),tr.select_one('[itemprop="value"]')]
  else:cells=tr.find_all(['td','th'],recursive=False)
  if len(cells)==2 and all(cells):
   k,v=map(text,cells)
   if k and v and len(k)<120 and len(v)<1000 and re.search(r'колич|число|волокон|диаметр|длина|ширина|высота|габарит|размер|масса|вес|материал|тип|категори|экран|оболоч|емкост|ёмкост|нагруз|усили|температур|защит|герметиз|кассет|разъем|разъём|затухан|коэффициент|частот|скорост|порт|мощност|питан|напряж|модель',k,re.I) and not re.search(r'цен|стоимост|налич|артикул|наименование',k,re.I):out['properties'][k]=v
 return makers.read_claims(out,s)

def init():
 with crm_store.connect() as c:
  c.execute('CREATE TABLE IF NOT EXISTS competitor_products(id TEXT PRIMARY KEY,provider TEXT,category TEXT,name TEXT,sku TEXT,payload TEXT,has_price INTEGER,updated TEXT)')
  c.execute('CREATE TABLE IF NOT EXISTS competitor_price_history(seq INTEGER PRIMARY KEY AUTOINCREMENT,product_id TEXT,checked TEXT,prices TEXT,fingerprint TEXT)')
  c.execute('CREATE TABLE IF NOT EXISTS competitor_jobs(id TEXT PRIMARY KEY,state TEXT,started REAL,finished TEXT,actor TEXT,phase TEXT,source TEXT)')
  c.execute('CREATE TABLE IF NOT EXISTS competitor_sources(id TEXT PRIMARY KEY,state TEXT,checked TEXT,last_success TEXT)')
  c.execute('CREATE TABLE IF NOT EXISTS competitor_makers(product_id TEXT PRIMARY KEY,maker_key TEXT NOT NULL,maker_label TEXT NOT NULL)')
  c.execute('CREATE INDEX IF NOT EXISTS competitor_maker_key ON competitor_makers(maker_key)')
  c.execute('CREATE TABLE IF NOT EXISTS competitor_search(id TEXT PRIMARY KEY,body TEXT NOT NULL,name TEXT NOT NULL,sku TEXT NOT NULL)')
  c.execute('CREATE INDEX IF NOT EXISTS competitor_provider ON competitor_products(provider)')
  c.execute('CREATE INDEX IF NOT EXISTS competitor_category ON competitor_products(category)')
  c.execute('CREATE INDEX IF NOT EXISTS competitor_history_product ON competitor_price_history(product_id,seq)')
 with crm_store.connect() as c:
  c.execute('CREATE TABLE IF NOT EXISTS competitor_price_quarantine(id INTEGER PRIMARY KEY AUTOINCREMENT,product_id TEXT,kind TEXT,payload TEXT,reason TEXT,quarantined TEXT)')
  c.execute('CREATE TABLE IF NOT EXISTS competitor_migrations(id TEXT PRIMARY KEY,applied TEXT)')
  if not c.execute('SELECT 1 FROM competitor_migrations WHERE id=?',(LANSET_PARSER,)).fetchone():
   ids=[]
   for id,payload in c.execute("SELECT id,payload FROM competitor_products WHERE provider='lanset'").fetchall():
    p=json.loads(payload)
    if p.get('priceParser')==LANSET_PARSER:continue
    ids.append(id);c.execute('INSERT INTO competitor_price_quarantine(product_id,kind,payload,reason,quarantined) VALUES(?,?,?,?,?)',(id,'product',payload,'Unscoped legacy Lanset parser',now()))
    p.update(prices=[],availability='',detailCheckedAt=None);p.pop('listingPrices',None)
    c.execute('UPDATE competitor_products SET payload=?,has_price=0 WHERE id=?',(json.dumps(p,ensure_ascii=False),id))
   for id in ids:
    for seq,checked,prices,fingerprint in c.execute('SELECT seq,checked,prices,fingerprint FROM competitor_price_history WHERE product_id=?',(id,)).fetchall():
     c.execute('INSERT INTO competitor_price_quarantine(product_id,kind,payload,reason,quarantined) VALUES(?,?,?,?,?)',(id,'history',json.dumps(dict(seq=seq,checked=checked,prices=json.loads(prices),fingerprint=fingerprint),ensure_ascii=False),'Unscoped legacy Lanset parser',now()))
    c.execute('DELETE FROM competitor_price_history WHERE product_id=?',(id,))
   c.execute('INSERT INTO competitor_migrations VALUES(?,?)',(LANSET_PARSER,now()))
 with crm_store.connect() as c:
  for id,name,path,payload in c.execute('SELECT id,name,category,payload FROM competitor_products').fetchall():
   p=json.loads(payload);group=category(name,p.get('categoryPath',''))
   if group!=path:
    p['category']=group;c.execute('UPDATE competitor_products SET category=?,payload=? WHERE id=?',(group,json.dumps(p,ensure_ascii=False),id))
 with crm_store.connect() as c:
  if not c.execute("SELECT 1 FROM competitor_migrations WHERE id='manufacturer-v2'").fetchone():
   for id,payload in c.execute('SELECT id,payload FROM competitor_products').fetchall():
    p=makers.enrich(json.loads(payload));c.execute('UPDATE competitor_products SET payload=? WHERE id=?',(json.dumps(p,ensure_ascii=False),id))
    c.execute('INSERT OR REPLACE INTO competitor_makers VALUES(?,?,?)',(id,p['manufacturerKey'],p['manufacturerLabel']))
    body,name,sku=search.document(p,BY_SOURCE.get(p['provider'],{}).get('name',''))
    c.execute('INSERT OR REPLACE INTO competitor_search VALUES(?,?,?,?)',(id,body,name,sku))
   c.execute('INSERT INTO competitor_migrations VALUES(?,?)',('manufacturer-v2',now()))
 with crm_store.connect() as c:
  if not c.execute("SELECT 1 FROM competitor_migrations WHERE id='search-v2'").fetchone():
   for id,payload in c.execute('SELECT id,payload FROM competitor_products').fetchall():
    record=json.loads(payload);body,name,sku=search.document(record,BY_SOURCE.get(record['provider'],{}).get('name',''))
    c.execute('INSERT OR REPLACE INTO competitor_search VALUES(?,?,?,?)',(id,body,name,sku))
   c.execute('INSERT INTO competitor_migrations VALUES(?,?)',('search-v2',now()))
 bootstrap=ROOT/'app/competitors/bootstrap.json'
 if bootstrap.exists():
  for record in json.loads(bootstrap.read_text()):
   with crm_store.connect() as c:exists=c.execute('SELECT 1 FROM competitor_products WHERE id=?',(record['id'],)).fetchone()
   if not exists:save(record)

def save(record,connection=None):
 record={**record,'category':category(record['name'],record.get('categoryPath',''))}
 if record.get('provider')=='lanset' and record.get('priceParser')!=LANSET_PARSER:
  record={**record,'prices':[],'availability':'','detailCheckedAt':None}
 listing_update=not record.get('detailCheckedAt')
 with (contextlib.nullcontext(connection) if connection is not None else crm_store.connect()) as c:
  old=c.execute('SELECT payload FROM competitor_products WHERE id=?',(record['id'],)).fetchone()
  if old:
   previous=json.loads(old[0])
   if not record.get('detailCheckedAt'):
    record['properties']=previous.get('properties',{});record['manufacturer']=previous.get('manufacturer','');record['detailCheckedAt']=previous.get('detailCheckedAt');record['sku']=record['sku'] or previous.get('sku','')
    if previous.get('detailCheckedAt'):
     record['listingPrices']=record['prices'];record['prices']=previous.get('prices',[]);record['checkedAt']=previous['checkedAt']
   if listing_update:
    for field in ['manufacturerDeclaration','brandDeclaration','originCountry','originEvidence']:
     if field not in record and field in previous:record[field]=previous[field]
  record=makers.enrich(record)
  c.execute('INSERT OR REPLACE INTO competitor_makers VALUES(?,?,?)',(record['id'],record['manufacturerKey'],record['manufacturerLabel']))
  serialized=json.dumps(record,ensure_ascii=False)
  c.execute('INSERT OR REPLACE INTO competitor_products VALUES(?,?,?,?,?,?,?,?)',(record['id'],record['provider'],record['category'],record['name'],record['sku'],serialized,int(bool(record['prices'])),record['checkedAt']))
  body,name,sku=search.document(record,BY_SOURCE.get(record['provider'],{}).get('name',''))
  c.execute('INSERT OR REPLACE INTO competitor_search VALUES(?,?,?,?)',(record['id'],body,name,sku))
  raw=json.dumps(record['prices'],ensure_ascii=False,sort_keys=True);fingerprint=hashlib.sha256(raw.encode()).hexdigest();prior=c.execute('SELECT fingerprint FROM competitor_price_history WHERE product_id=? ORDER BY seq DESC LIMIT 1',(record['id'],)).fetchone()
  if record.get('checkedAt') and (not prior or prior[0]!=fingerprint):c.execute('INSERT INTO competitor_price_history(product_id,checked,prices,fingerprint) VALUES(?,?,?,?)',(record['id'],record['checkedAt'],raw,fingerprint))

def save_many(records):
 with crm_store.connect() as connection:
  for record in records:save(record,connection)

def source_state(id,state):
 with crm_store.connect() as c:
  prior=c.execute('SELECT last_success FROM competitor_sources WHERE id=?',(id,)).fetchone();stamp=now();c.execute('INSERT OR REPLACE INTO competitor_sources VALUES(?,?,?,?)',(id,state,stamp,stamp if state=='ok' else prior[0] if prior else None))
def scrape_source(src,full=True,progress=None):
 if src['id']=='kabis':
  from competitor_sources_extended import kabis_products
  try:
   page=1
   while True:
    records,pagination=kabis_products(src,fetch(src,src['publicApi']+'?page='+str(page)+'&limit=100'))
    for record in records:save(record)
    if progress:progress('catalog',src['id'])
    if page>=int(pagination.get('totalPages') or pagination.get('pages') or 1):break
    page+=1;time.sleep(.15)
   source_state(src['id'],'ok')
  except Exception:source_state(src['id'],'partial')
  return
 if src.get('priceDocument'):
  from competitor_sources_extended import document_products
  try:
   for record in document_products(src,fetch_bytes(src,src['priceDocument'])):save(record)
   source_state(src['id'],'ok')
  except Exception:source_state(src['id'],'partial')
  return
 if src['id']=='mircable':
  from competitor_sources_extra import mircable
  try:
   for record in mircable(src,fetch(src,src['seeds'][0])):save(record)
   source_state(src['id'],'ok')
  except HTTPError as error:source_state(src['id'],'blocked' if error.code in (401,403,429) else 'partial')
  except Exception:source_state(src['id'],'partial')
  return
 queue=collections.deque(src['seeds']);scheduled=set(src['seeds']);seen=set();failed=False;found=0
 while queue:
  url=queue.popleft()
  if url in seen:continue
  seen.add(url)
  try:
   records,links=listing(src,url,fetch(src,url))
   found+=len(records)
   for record in records:save(record)
   for link in links:
    if link not in scheduled:queue.append(link);scheduled.add(link)
   if progress:progress('catalog',src['id'])
  except PermissionError:source_state(src['id'],'blocked');return
  except HTTPError as error:
   failed=True
   if error.code in (401,403,429):source_state(src['id'],'blocked');return
  except Exception:failed=True
  time.sleep(.15)
 if full:
  with crm_store.connect() as c:records=[json.loads(r[0]) for r in c.execute('SELECT payload FROM competitor_products WHERE provider=?',(src['id'],))]
  for record in records:
   try:save(details(src,record,fetch(src,record['url'])))
   except PermissionError:source_state(src['id'],'blocked');return
   except HTTPError as error:
    failed=True
    if error.code in (401,403,429):source_state(src['id'],'blocked');return
   except Exception:failed=True
   if progress:progress('details',src['id'])
   time.sleep(.15)
 source_state(src['id'],'partial' if failed or not found else 'ok')

def run(job,source_ids,full):
 def progress(phase,source):
  with crm_store.connect() as c:c.execute('UPDATE competitor_jobs SET phase=?,source=? WHERE id=?',(phase,source,job))
 try:
  with ThreadPoolExecutor(max_workers=7) as pool:
   for future in as_completed([pool.submit(scrape_source,BY_SOURCE[id],full,progress) for id in source_ids]):future.result()
  state='completed'
 except Exception:state='error'
 with crm_store.connect() as c:c.execute('UPDATE competitor_jobs SET state=?,finished=? WHERE id=?',(state,now(),job))

def start(actor,source_ids=None,full=True,background=True):
 if source_ids is None:source_ids=list(BY_SOURCE)
 if not isinstance(source_ids,list) or not source_ids or any(id not in BY_SOURCE for id in source_ids):raise ValueError('Unknown source')
 with crm_store.connect() as c:
  c.execute('BEGIN IMMEDIATE');prior=c.execute('SELECT id,state,started FROM competitor_jobs ORDER BY started DESC LIMIT 1').fetchone()
  if prior and prior[1]=='running' and time.time()-prior[2]<21600:return prior[0]
  if prior and time.time()-prior[2]<30:return prior[0]
  job=uuid.uuid4().hex;c.execute('INSERT INTO competitor_jobs VALUES(?,?,?,?,?,?,?)',(job,'running',time.time(),None,actor,'catalog',''))
 if background:threading.Thread(target=run,args=(job,list(dict.fromkeys(source_ids)),full),daemon=True).start()
 else:run(job,list(dict.fromkeys(source_ids)),full)
 return job

def schedule_due():
 with crm_store.connect() as c:row=c.execute('SELECT started FROM competitor_jobs ORDER BY started DESC LIMIT 1').fetchone()
 return not row or time.time()-row[0]>=86400

def register(app,owner):
 from flask import jsonify,request,g,send_from_directory,redirect
 init()
 @app.get('/competitors')
 def competitors_redirect():return redirect('/competitors/')
 @app.get('/competitors/')
 def competitors_index():return send_from_directory(ROOT/'app/competitors','index.html')
 @app.get('/competitors/api/products')
 def competitor_products():
  try:page=max(1,min(100000,int(request.args.get('page','1'))))
  except ValueError:return jsonify(error='Некорректная страница'),400
  clauses=[];args=[]
  for key in ['provider','category']:
   value=request.args.get(key,'')
   if value:clauses.append('p.'+key+'=?');args.append(value)
  region=request.args.get('region','')
  if region:
   ids=[s['id'] for s in SOURCES if source_in_region(s['id'],region)]
   if ids:clauses.append('p.provider IN ('+','.join('?' for _ in ids)+')');args.extend(ids)
   else:clauses.append('0')
  q=request.args.get('q','').strip()[:200];words=search.terms(q)
  if q and not words:clauses.append('0')
  for word in words:clauses.append('instr(s.body,?)>0');args.append(word)
  if request.args.get('priced')=='1':clauses.append('has_price=1')
  manufacturer=request.args.get('manufacturer','')
  if manufacturer:clauses.append('m.maker_key=?');args.append(manufacturer)
  rank_args=[];rank='p.name,p.provider'
  if words:
   phrase=search.normalize(q);rank_args=[phrase,phrase,phrase]
   rank="(CASE WHEN replace(s.sku,' ','')=replace(?,' ','') THEN 100 ELSE 0 END+CASE WHEN s.name=? THEN 80 ELSE 0 END+CASE WHEN instr(s.name,?)>0 THEN 40 ELSE 0 END"
   for word in words:
    rank+='+CASE WHEN instr(s.sku,?)>0 THEN 20 ELSE 0 END+CASE WHEN instr(s.name,?)>0 THEN 30 ELSE 0 END';rank_args.extend([word,word])
   rank+=') DESC,p.name,p.provider'
  sql='SELECT p.payload FROM competitor_products p JOIN competitor_search s ON s.id=p.id JOIN competitor_makers m ON m.product_id=p.id'+(' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY '+rank+' LIMIT 21 OFFSET ?'
  with crm_store.connect() as c:
   manufacturer_options=[{'id':key,'name':label} for key,label in c.execute('SELECT DISTINCT m.maker_key,m.maker_label FROM competitor_makers m JOIN competitor_products p ON p.id=m.product_id ORDER BY m.maker_label')]
   rows=c.execute(sql,args+rank_args+[(page-1)*20]).fetchall();states={r[0]:dict(zip(['state','checkedAt','lastSuccess'],r[1:])) for r in c.execute('SELECT * FROM competitor_sources')};job=c.execute('SELECT id,state,started,finished,phase,source FROM competitor_jobs ORDER BY started DESC LIMIT 1').fetchone()
  products=[json.loads(r[0]) for r in rows[:20]]
  for p in products:
   p['searchMatches']=search.highlights(p,words,BY_SOURCE.get(p['provider'],{}).get('name','')) if words else []
   p['supplierPresence']=PRESENCE.get(p['provider'],{})
  return jsonify(products=products,hasNext=len(rows)>20,page=page,categories=CATEGORIES,regions=REGIONS,manufacturers=manufacturer_options,sources=[{**s,'presence':PRESENCE.get(s['id'],{}),'matchesRegion':source_in_region(s['id'],region),'status':states.get(s['id'])} for s in SOURCES],job=dict(zip(['id','state','started','finished','phase','source'],job)) if job else None,canRefresh=g.user.get('role')=='admin' and g.user.get('login')==owner)
 @app.get('/competitors/api/product/<id>')
 def competitor_product(id):
  with crm_store.connect() as c:
   row=c.execute('SELECT payload FROM competitor_products WHERE id=?',(id,)).fetchone();history=[dict(zip(['checkedAt','prices'],(r[0],json.loads(r[1])))) for r in c.execute('SELECT checked,prices FROM competitor_price_history WHERE product_id=? ORDER BY seq DESC LIMIT 100',(id,))]
  return (jsonify(product=json.loads(row[0]),history=history) if row else (jsonify(error='Товар не найден'),404))
 @app.post('/competitors/api/manufacturers')
 def competitor_manufacturer_metadata():
  if g.user.get('role')!='admin' or g.user.get('login')!=owner:return jsonify(error='Доступно только владельцу портала'),403
  payload=request.get_json(silent=True);allowed={'manufacturerDeclaration','brandDeclaration','originCountry','originEvidence','manufacturerClaimsCheckedAt'}
  if not isinstance(payload,dict) or not isinstance(payload.get('items'),list) or len(payload['items'])>1000:return jsonify(error='Некорректные данные'),400
  items=payload['items']
  if any(not isinstance(item,dict) or set(item)-({'id'}|allowed) or not re.fullmatch(r'[a-f0-9]{20}',str(item.get('id',''))) or any(not isinstance(v,str) or len(v)>200 for k,v in item.items() if k!='id') for item in items):return jsonify(error='Некорректные поля'),400
  with crm_store.connect() as c:
   c.execute('BEGIN IMMEDIATE');records=[]
   for item in items:
    row=c.execute('SELECT payload FROM competitor_products WHERE id=?',(item['id'],)).fetchone()
    if row is None:return jsonify(error='Товар не найден'),404
    record=json.loads(row[0]);record.update({k:v for k,v in item.items() if k in allowed});records.append(makers.enrich(record))
   for record in records:
    c.execute('UPDATE competitor_products SET payload=? WHERE id=?',(json.dumps(record,ensure_ascii=False),record['id']))
    c.execute('INSERT OR REPLACE INTO competitor_makers VALUES(?,?,?)',(record['id'],record['manufacturerKey'],record['manufacturerLabel']))
    body,name,sku=search.document(record,BY_SOURCE.get(record['provider'],{}).get('name',''))
    c.execute('INSERT OR REPLACE INTO competitor_search VALUES(?,?,?,?)',(record['id'],body,name,sku))
  return jsonify(updated=len(records))

 @app.post('/competitors/api/refresh')
 def competitor_refresh():
  if g.user.get('role')!='admin' or g.user.get('login')!=owner:return jsonify(error='Доступно только владельцу портала'),403
  payload=request.get_json(silent=True)
  if payload is None:payload={}
  if not isinstance(payload,dict):return jsonify(error='Некорректный запрос'),400
  try:job=start(g.user['login'],payload.get('sources'),True)
  except (ValueError,TypeError):return jsonify(error='Неизвестный источник'),400
  return jsonify(jobId=job),202

 @app.post('/competitors/api/import')
 def competitor_import():
  if g.user.get('role')!='admin' or g.user.get('login')!=owner:return jsonify(error='Доступно только владельцу портала'),403
  request.max_content_length=10_000_000
  payload=request.get_json(silent=True)
  if not isinstance(payload,dict) or not isinstance(payload.get('products'),list) or len(payload['products'])>20000:return jsonify(error='Некорректные данные'),400
  records=[]
  for record in payload['products']:
   if not isinstance(record,dict) or record.get('provider') not in BY_SOURCE:return jsonify(error='Неизвестный источник'),400
   src=BY_SOURCE[record['provider']]
   if src['id']=='etm':
    from competitor_sources_extended import scope_allowed
    if not scope_allowed(src,record.get('sourceCategoryUrl','')):return jsonify(error='Товар вне разрешённого раздела ЭТМ'),400
   if not safe_url(src,record.get('url','')) or not isinstance(record.get('name'),str) or not record['name'].strip() or not record.get('checkedAt'):return jsonify(error='Некорректный товар'),400
   source_id=record.get('sourceProductId','') if src['id']=='mircable' or src.get('priceDocument') else ''
   if (src['id']=='mircable' or src.get('priceDocument')) and (not isinstance(source_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,160}',source_id)):return jsonify(error='Некорректный идентификатор'),400
   if record.get('id')!=product_id(src,canonical(src,record['url']),source_id):return jsonify(error='Некорректный идентификатор'),400
   if not isinstance(record.get('prices'),list) or len(record['prices'])>1000:return jsonify(error='Некорректные цены'),400
   for row in record['prices']:
    if not isinstance(row,dict) or not money(row.get('amount','')) or row.get('currency','') not in ('','RUB','RUR','USD','EUR'):return jsonify(error='Некорректная цена'),400
   records.append(record)
  save_many(records)
  return jsonify(imported=len(records))
