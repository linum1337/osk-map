"""Public supplier prices for catalogue products, fetched only on explicit refresh."""
import json,re,time,threading,uuid,os,ssl,certifi
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
from urllib.request import Request,build_opener,HTTPRedirectHandler,HTTPSHandler
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor,as_completed
from bs4 import BeautifulSoup
import crm_store
ROOT=Path(__file__).resolve().parent
HOSTS={'volsip.ru','ssd.ru','componentltd.ru','shop.nag.ru','fibertool.ru'}
MAX_BYTES=8_000_000

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def norm(s):return re.sub(r'[^а-яa-z0-9]','',str(s).lower().replace('ё','е'))
def text(n):return n.get_text(' ',strip=True) if n else ''
def money(s):
 raw=str(s).strip()
 if re.search(r'[-−]\s*\d',raw):return None
 parts=re.findall(r'\d[\d \u00a0\u202f]*(?:[,.]\d+)?',raw)
 if len(parts)!=1:return None
 s=re.sub(r'[^\d,.]','',parts[0]).replace(',','.')
 try:
  value=Decimal(s)
  return str(value.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)) if value.is_finite() and value>0 else None
 except (InvalidOperation,ValueError):return None

def catalogue():return {e['id']:e for e in json.loads((ROOT/'app/references/closures/closures.json').read_text())['entries']}
def valid_url(url,host=None):
 p=urlsplit(url)
 return p.scheme=='https' and p.hostname in HOSTS and (host is None or p.hostname==host) and p.port in (None,443) and not p.username and not p.password
class SafeRedirect(HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if not valid_url(newurl,urlsplit(req.full_url).hostname):raise ValueError('Supplier redirect outside product host')
  return super().redirect_request(req,fp,code,msg,headers,newurl)
def fetch(entry):
 url=entry['url']
 if not valid_url(url):raise ValueError('Unsupported product URL')
 req=Request(url,headers={'User-Agent':'OSK-Product-Reference/1.0 (+https://osk.l1num.ru/)','Accept':'text/html','Accept-Language':'ru,en;q=0.5'})
 context=ssl.create_default_context();context.load_verify_locations(cafile=certifi.where())
 with build_opener(SafeRedirect(),HTTPSHandler(context=context)).open(req,timeout=12) as r:
  if not valid_url(r.url,urlsplit(url).hostname):raise ValueError('Unexpected response URL')
  raw=r.read(MAX_BYTES+1)
  if len(raw)>MAX_BYTES:raise ValueError('Supplier response exceeds size limit')
  return raw.decode(r.headers.get_content_charset() or 'utf-8',errors='replace')

def parse(entry,html):
 s=BeautifulSoup(html,'html.parser');supplier=entry['supplier'];prices=[];seen=set()
 # Category cards do not identify a specific purchasable modification.
 if supplier=='Volsip' and not s.select_one('.prod_price #block_price'):return []
 h=s.select_one('h1');name=norm(entry['name']);heading=norm(text(h))
 if heading and not (name in heading or heading in name):
  raise ValueError('Product heading differs from catalogue')
 def add(label,amount,currency='RUB',unit='',tax='',condition=''):
  value=money(amount)
  if not value:return
  if str(amount).strip().lower().startswith('от '):condition='от '+value+(' · '+condition if condition else '')
  key=(label,value,currency,unit,tax,condition)
  if key in seen:return
  seen.add(key);prices.append({'label':label or 'Цена на странице','amount':value,'currency':currency or 'RUB','unit':unit,'tax':tax,'condition':condition})
 def tables(scope,tax=''):
  for row in scope.select('.data-table__body .data-table__row'):
   cells=row.select('.data-table__td');head=row.find_parent(class_='data-table');headers=[text(c) for c in head.select('.data-table__head .data-table__th')] if head else []
   if len(cells)>=2:
    for i,c in enumerate(cells[1:],1):
     if '₽' in text(c):add(text(cells[0]),text(c),tax=headers[i] if i<len(headers) else tax)
  for row in scope.select('.data-list__row'):
   label=row.select_one('.data-list__title');value=row.select_one('.data-list__value')
   if label and value and re.search(r'₽|руб',text(value),re.I):add(text(label),text(value),tax=tax)
 if supplier=='Volsip':
  block=s.select_one('.prod_price #block_price');add('Цена на странице',text(block),unit='₽')
  scope=block.find_parent('form') or block.parent
  for row in scope.select('.price_tier tr, .price_bulk tr, .jshop_price_extra tr'):
   cells=row.find_all(['td','th'])
   if len(cells)>=2:add(text(cells[0]),text(cells[-1]),condition=text(cells[0]))
 elif supplier=='ССД':
  scope=s.select_one('.product-aside__block_price')
  if scope:
   main=scope.select_one('.product__price-value');add('Цена на странице',text(main),unit='шт',tax=text(scope.select_one('.product__price-title')))
   # VAT tooltips are explicitly separate price categories.
   no_vat=scope.select_one('.price-without-nds-tooltip')
   if no_vat:tables(no_vat,'Без НДС');no_vat.decompose()
   tables(scope,'С НДС' if 'С НДС' in text(scope) else '')
 elif supplier=='Компонент':
  scope=s.select_one('.card__data')
  if scope:
   for group in scope.select('[class*="price-group"], [class*="price_group"]'):
    value=group.select_one('[itemprop="price"], .price_value');add(text(group.select_one('[class*="name"]')),value.get('content') or text(value) if value else '')
   if not prices:
    value=scope.select_one('[itemprop="price"]');cur=scope.select_one('[itemprop="priceCurrency"]')
    if value:add('Цена на странице',value.get('content') or text(value),cur.get('content') if cur else 'RUB')
 elif supplier=='НАГ':
  scope=s.select_one('.product-card__prices')
  if scope:
   value=scope.select_one('[itemprop="price"]');cur=scope.select_one('[itemprop="priceCurrency"]')
   if value:add('Цена на странице',value.get('content') or text(value),cur.get('content') if cur else 'RUB',unit='шт')
   tables(scope)
 elif supplier=='Fibertool':
  scope=s.select_one('.item_main_info')
  if scope:
   for group in scope.select('.cost .price_group'):
    label=text(group.select_one('.price_name'))
    for price in group.select('.price_matrix_wrapper .price'):
     value=price.select_one('.price_value');condition=text(price.select_one('.price_interval, .price_range'))
     add(label,text(value) or price.get('data-value'),price.get('data-currency','RUB'),text(price.select_one('.price_measure')),condition=condition)
 return prices

def init():
 with crm_store.connect() as c:
  c.execute('CREATE TABLE IF NOT EXISTS closure_supplier_prices(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS closure_price_jobs(id TEXT PRIMARY KEY,state TEXT,started REAL,finished TEXT,total INTEGER,done INTEGER,actor TEXT)')
def snapshot():
 with crm_store.connect() as c:
  prices={id:json.loads(raw) for id,raw in c.execute('SELECT id,payload FROM closure_supplier_prices')}
  row=c.execute('SELECT id,state,started,finished,total,done FROM closure_price_jobs ORDER BY started DESC LIMIT 1').fetchone()
  if row and row[1]=='running' and time.time()-row[2]>1800:
   c.execute("UPDATE closure_price_jobs SET state='interrupted',finished=? WHERE id=?",(now(),row[0]));row=(row[0],'interrupted',row[2],now(),row[4],row[5])
 return {'prices':prices,'job':dict(zip(['id','state','started','finished','total','done'],row)) if row else None}
def refresh_one(entry):
 checked=now()
 try:
  prices=parse(entry,fetch(entry));payload={'id':entry['id'],'source':entry['url'],'checkedAt':checked,'status':'ok' if prices else 'unavailable','prices':prices}
 except Exception:
  # Failed refresh never relabels an earlier price as current.
  with crm_store.connect() as c:row=c.execute('SELECT payload FROM closure_supplier_prices WHERE id=?',(entry['id'],)).fetchone()
  old=json.loads(row[0]) if row else {};payload={'id':entry['id'],'source':entry['url'],'checkedAt':old.get('checkedAt'),'attemptedAt':checked,'status':'error','prices':old.get('prices',[])}
 with crm_store.connect() as c:c.execute('INSERT OR REPLACE INTO closure_supplier_prices VALUES(?,?)',(entry['id'],json.dumps(payload,ensure_ascii=False)))
 return payload

def run(job_id,entries):
 try:
  with ThreadPoolExecutor(max_workers=4) as pool:
   for f in as_completed([pool.submit(refresh_one,e) for e in entries]):
    f.result()
    with crm_store.connect() as c:c.execute('UPDATE closure_price_jobs SET done=done+1 WHERE id=?',(job_id,))
  state='completed'
 except Exception:state='error'
 with crm_store.connect() as c:c.execute('UPDATE closure_price_jobs SET state=?,finished=? WHERE id=?',(state,now(),job_id))
def start(actor,ids=None,background=True):
 entries=catalogue()
 if ids is not None:
  if not isinstance(ids,list) or not ids or len(ids)>len(entries) or any(not isinstance(i,str) or i not in entries for i in ids):raise ValueError('Unknown product IDs')
  entries={i:entries[i] for i in dict.fromkeys(ids)}
 with crm_store.connect() as c:
  c.execute('BEGIN IMMEDIATE');row=c.execute("SELECT id,started FROM closure_price_jobs WHERE state='running' ORDER BY started DESC LIMIT 1").fetchone()
  if row and time.time()-row[1]<1800:return row[0]
  recent=c.execute('SELECT id,started FROM closure_price_jobs ORDER BY started DESC LIMIT 1').fetchone()
  if recent and time.time()-recent[1]<30:return recent[0]
  job_id=uuid.uuid4().hex;c.execute('INSERT INTO closure_price_jobs VALUES(?,?,?,?,?,?,?)',(job_id,'running',time.time(),None,len(entries),0,actor))
 if background:threading.Thread(target=run,args=(job_id,list(entries.values())),daemon=True).start()
 else:run(job_id,list(entries.values()))
 return job_id

def schedule_due(timestamp=None):
 timestamp=time.time() if timestamp is None else timestamp
 with crm_store.connect() as c:row=c.execute("SELECT state,started FROM closure_price_jobs ORDER BY started DESC LIMIT 1").fetchone()
 return not row or timestamp-row[1]>=86400 or (row[0]=='running' and timestamp-row[1]>1800) or row[0]=='interrupted'

_scheduler_started=False
def start_scheduler():
 global _scheduler_started
 if _scheduler_started or os.environ.get('CLOSURE_PRICES_AUTOMATIC','1')=='0':return
 _scheduler_started=True
 def loop():
  while True:
   try:
    if schedule_due():start('automatic-daily')
   except Exception:pass
   time.sleep(30)
 threading.Thread(target=loop,name='closure-daily-prices',daemon=True).start()

def register(app,admin_name):
 from flask import jsonify,request,g
 init()
 @app.get('/references/closures/api/prices')
 def closure_price_snapshot():return jsonify(**snapshot(),canRefresh=g.user.get('role')=='admin' and g.user.get('login')==admin_name,refreshIntervalSeconds=86400)
 @app.post('/references/closures/api/prices/refresh')
 def closure_price_refresh():
  if g.user.get('role')!='admin' or g.user.get('login')!=admin_name:return jsonify(error='Обновление доступно только владельцу портала'),403
  payload=request.get_json(silent=True)
  if payload is None:payload={}
  if not isinstance(payload,dict):return jsonify(error='Некорректный запрос'),400
  try:job=start(g.user['login'],payload.get('ids'))
  except ValueError:return jsonify(error='Неизвестная муфта'),400
  return jsonify(jobId=job),202
