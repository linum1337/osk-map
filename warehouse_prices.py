"""Private price catalogue. No supplier prices or workbook content in source control."""
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import auth_store
import crm_store
import warehouse_store as stock

def init():
 with crm_store.connect() as c:
  c.execute('CREATE TABLE IF NOT EXISTS warehouse_prices(id INTEGER PRIMARY KEY CHECK(id=1), digest TEXT NOT NULL, data TEXT NOT NULL, actor TEXT NOT NULL, updated_at INTEGER NOT NULL)')

def allowed(user):
 return user.get('role')!='warehouse' and auth_store.normalize(user.get('login',''))!=auth_store.normalize('Валерия Алексеева')

def match_key(data):
 # Exact specification only. Decimal spelling and the known manufacturer suffix
 # do not change the specification; diameter, load and rod always remain in key.
 construction=data.get('construction') or data.get('marking') or ''
 construction=re.sub(r'\s*(?:ультракабель|ультркабель|ск)\s*$','',construction.casefold())
 construction=re.sub(r'\s+','',construction).replace(',','.')
 construction=re.sub(r'(окпд-)0+(\d)',r'\1\2',construction)
 rod=re.sub(r'\s+','',data.get('rod','').casefold()).replace(',','.').translate(str.maketrans({'е':'e','а':'a'}))
 def decimal(m):return format(Decimal(m[0]).normalize(),'f')
 return re.sub(r'\d+(?:\.\d+)?',decimal,construction)+'|'+re.sub(r'\d+(?:\.\d+)?',decimal,rod)

def amounts(value):
 base=Decimal(str(value))/1000
 return {key:format((base*factor).quantize(Decimal('.01'),rounding=ROUND_HALF_UP),'f') for key,factor in [('base',Decimal(1)),('plus10',Decimal('1.10')),('plus15',Decimal('1.15')),('plus20',Decimal('1.20')),('plus30',Decimal('1.30'))]}

def catalogue():
 with crm_store.connect() as c:row=c.execute('SELECT digest,data,updated_at FROM warehouse_prices WHERE id=1').fetchone()
 if not row:return {'version':None,'rows':[],'source':'','title':'Прайс ещё не загружен','unit':'₽/м с НДС'}
 data=json.loads(row[1]);data.update(version=row[0],updatedAt=row[2],unit='₽/м с НДС')
 for r in data['rows']:r['prices']=amounts(r['pricePerKm'])
 return data

def decorate(snapshot,user):
 snapshot['canViewPrices']=allowed(user)
 if not snapshot['canViewPrices']:return snapshot
 cat=catalogue();lookup={match_key(r):r for r in cat['rows']}
 snapshot['priceVersion']=cat['version'];snapshot['priceTitle']=cat['title']
 for r in snapshot['items']+snapshot['groups']:
  match=lookup.get(match_key(r));r['prices']=match['prices'] if match else None
  if match:r['priceSourceRow']=match['sourceRow']
 return snapshot

def import_prices(body,user):
 if not isinstance(body,dict) or body.get('format')!='osk-warehouse-prices-v1':return 400,{'error':'Неверный формат прайса'}
 rows=body.get('rows');digest=body.get('sourceDigest');source=body.get('source');title=body.get('title')
 if not isinstance(rows,list) or not 1<=len(rows)<=10000 or not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):return 400,{'error':'Проверьте строки прайса и источник'}
 if not all(isinstance(v,str) and 1<=len(v)<=300 for v in [source,title]):return 400,{'error':'Укажите название прайса'}
 clean=[];keys=set();source_rows=set()
 try:
  for r in rows:
   if not isinstance(r,dict) or type(r.get('sourceRow')) is not int or not 1<=r['sourceRow']<=1048576 or r['sourceRow'] in source_rows:raise ValueError()
   source_rows.add(r['sourceRow'])
   if not all(isinstance(r.get(k),str) and len(r[k])<=500 for k in ['construction','rod','category','cableDiameter','weight','type']):raise ValueError()
   if not r['construction'].strip() or not r['rod'].strip():raise ValueError()
   price=Decimal(str(r['pricePerKm']))
   if not price.is_finite() or price<=0 or price>1000000000 or price*100!=(price*100).to_integral_value():raise ValueError()
   key=match_key(r)
   if key in keys:raise ValueError()
   keys.add(key);clean.append({k:r[k] for k in ['sourceRow','construction','rod','category','cableDiameter','weight','type']}|{'pricePerKm':format(price,'f')})
 except (ValueError,KeyError,TypeError,InvalidOperation):return 400,{'error':'Некорректная или повторяющаяся строка прайса'}
 data={'source':source,'title':title,'rows':clean}
 with crm_store.connect() as c:
  c.execute('BEGIN IMMEDIATE')
  previous=c.execute('SELECT digest FROM warehouse_prices WHERE id=1').fetchone()
  if previous and previous[0]==digest:return 200,{'imported':False,'rows':len(clean)}
  c.execute('INSERT INTO warehouse_prices VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET digest=excluded.digest,data=excluded.data,actor=excluded.actor,updated_at=excluded.updated_at',(digest,json.dumps(data,ensure_ascii=False),user['login'],stock.now_ms()))
 return 201,{'imported':True,'rows':len(clean)}
