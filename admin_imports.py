"""Bounded Excel parsing, reviewable plans and confirmed administration imports."""
from decimal import Decimal,InvalidOperation
from io import BytesIO
import hashlib,json,re,secrets,zipfile
import openpyxl
import admin_store,crm_store,warehouse_store as stock,warehouse_prices as prices,warehouse_update

class ImportProblem(ValueError):pass

def text(value):return '' if value is None else str(value).strip()
def norm(value):return re.sub(r'\s+','',text(value).casefold())
def number(value,label):
 try:
  value=Decimal(text(value).replace('\u00a0','').replace(' ','').replace(',','.'))
  if not value.is_finite() or value<=0:raise ValueError()
  return value
 except (ValueError,InvalidOperation):raise ImportProblem('Проверьте '+label+': требуется положительное число')

def workbook(content):
 if not isinstance(content,bytes) or not content or len(content)>10_000_000:raise ImportProblem('Выберите Excel-файл размером до 10 МБ')
 try:
  with zipfile.ZipFile(BytesIO(content)) as archive:
   entries=archive.infolist()
   if len(entries)>3000 or sum(r.file_size for r in entries)>40_000_000:raise ImportProblem('Файл слишком большой для загрузки')
   if any('vbaproject' in r.filename.lower() for r in entries):raise ImportProblem('Загрузите обычный .xlsx без макросов')
  book=openpyxl.load_workbook(BytesIO(content),data_only=True,read_only=False,keep_links=False)
 except ImportProblem:raise
 except Exception:raise ImportProblem('Не удалось прочитать Excel. Нужен обычный файл .xlsx')
 sheet=book.active
 if sheet.max_row>10000 or sheet.max_column>64:raise ImportProblem('В файле слишком много строк или столбцов')
 return book,sheet

def stock_payload(sheet,source,digest):
 header_row=None
 for i,row in enumerate(sheet.iter_rows(min_row=1,max_row=min(sheet.max_row,20),values_only=True),1):
  normalized=[norm(v) for v in row]
  if any('катуш' in v for v in normalized) and any('длина' in v for v in normalized):header_row=i;break
 if header_row is None:raise ImportProblem('Не найдены заголовки «№ катушки» и «Длина/км» или «Длина/м»')
 # Source warehouse has eight fixed columns, including an unlabelled storage column.
 if not ('катуш' in norm(sheet.cell(header_row,2).value) and 'длина' in norm(sheet.cell(header_row,3).value)):raise ImportProblem('Нужен складской файл: паллет, катушка, длина, конструкция, маркировка, примечание, пруток, место хранения')
 unit_header=norm(sheet.cell(header_row,3).value)
 if 'км' in unit_header:unit='км';factor=1000
 elif re.search(r'(?:/|,|\(|\b)м(?:\)|$)',unit_header):unit='м';factor=1
 else:raise ImportProblem('Укажите единицу длины в заголовке: «Длина/км» или «Длина/м»')
 merged={}
 for area in sheet.merged_cells.ranges:
  if area.min_col==1:
   for i in range(area.min_row,min(area.max_row,sheet.max_row)+1):merged[i]=sheet.cell(area.min_row,1).value
 items=[]
 for i in range(header_row+1,sheet.max_row+1):
  values=[sheet.cell(i,j).value for j in range(1,9)]
  if not (values[1] is not None or values[3] or values[4]):continue
  length=number(values[2],'длину в строке '+str(i))*factor
  if length>100000000 or length*1000!=(length*1000).to_integral_value():raise ImportProblem('Проверьте точность длины в строке '+str(i))
  items.append({'sourceRow':i,'pallet':text(merged.get(i,values[0])),'reel':text(values[1]),'length':format(length,'f'),'sourceLength':values[2],'sourceUnit':unit,'construction':text(values[3]),'marking':text(values[4]),'note':text(values[5]),'rod':text(values[6]),'location':text(values[7])})
 if not items:raise ImportProblem('В файле нет складских позиций')
 return {'format':'osk-krasnodar-stock-update-v1','source':source,'sourceDigest':digest,'sourceData':{'sheet':sheet.title,'lengthUnit':unit,'cachedRows':[list(row) for row in sheet.iter_rows(values_only=True)]},'items':items}

def prices_payload(sheet,source,digest):
 headers=None;title='Прайс '+source
 for i in range(1,min(sheet.max_row,30)+1):
  values=[norm(c.value) for c in sheet[i]]
  if any('цены' in v and 'ндс' in v for v in values):title=next(text(sheet.cell(i,j+1).value) for j,v in enumerate(values) if 'цены' in v and 'ндс' in v)
  name=next((j+1 for j,v in enumerate(values) if v in ('наименованиеультра','маркировка')),None)
  rod=next((j+1 for j,v in enumerate(values) if 'диаметрпрутка' in v),None)
  price=next((j+1 for j,v in enumerate(values) if 'цена' in v and ('1км' in v or '/км' in v)),None)
  if name and rod and price:
   headers={'name':name,'rod':rod,'price':price,'diameter':next((j+1 for j,v in enumerate(values) if 'диаметркабеля' in v),None),'weight':next((j+1 for j,v in enumerate(values) if 'вес' in v),None),'type':next((j+1 for j,v in enumerate(values) if v=='тип'),None)};start=i;break
 if headers is None:raise ImportProblem('Загрузите исходный прайс с наименованием, диаметром прутка и ценой за 1 км. Сокращённый прайс для скачивания не подходит для обновления.')
 category='';rows=[];seen=set()
 for i in range(start+1,sheet.max_row+1):
  name=text(sheet.cell(i,headers['name']).value);raw=sheet.cell(i,headers['price']).value
  if name.casefold().startswith('пруток '):category=name;continue
  if not name or 'наименование' in name.casefold():continue
  if raw is None:
   if prices.match_key({'construction':name,'rod':text(sheet.cell(i,headers['rod']).value)}):raise ImportProblem('В строке '+str(i)+' нет числовой цены. Пересчитайте и сохраните файл в Excel.')
   continue
  price=number(raw,'цену в строке '+str(i))
  if price>1000000000 or price*100!=(price*100).to_integral_value():raise ImportProblem('Проверьте точность цены в строке '+str(i))
  row={'sourceRow':i,'construction':name,'rod':text(sheet.cell(i,headers['rod']).value),'category':category,'pricePerKm':format(price,'f')}
  for field,col in [('cableDiameter','diameter'),('weight','weight'),('type','type')]:row[field]=text(sheet.cell(i,headers[col]).value) if headers[col] else ''
  key=prices.match_key(row)
  if not key or key in seen:raise ImportProblem('Не распознаны волокна/пруток или повторяется цена в строке '+str(i))
  seen.add(key);rows.append(row)
 if not rows:raise ImportProblem('В файле не найдены строки с ценами')
 return {'format':'osk-warehouse-prices-v1','source':source,'sourceDigest':digest,'title':title,'rows':rows}

def identity(row):
 # Identity keeps reel, metre length and full construction/rod. It does not use prices.
 return (row.get('reel','') if row.get('reel') not in ('?','') else '',Decimal(str(row['length'])),stock.product_key(row))

def plan_stock(payload,current):
 used=set();new=[];preserved=0;changes=[];changed_rows=0
 labels={'pallet':'Паллет','reel':'Катушка','construction':'Конструкция','marking':'Маркировка','note':'Примечание','rod':'Пруток','location':'Место хранения'}
 for row in payload['items']:
  options=[r for r in current if r['id'] not in used and identity(r)==identity(row)]
  if row.get('reel') not in ('','?'):
   same_reel=[r for r in current if r['id'] not in used and r.get('reel')==row['reel'] and Decimal(str(r['length']))==Decimal(row['length'])]
   if len(same_reel)==1:options=same_reel
  exact=[r for r in options if r.get('sourceRow')==row['sourceRow']]
  if exact:match=exact[0]
  elif len(options)==1:match=options[0]
  elif len(options)>1:raise ImportProblem('Неоднозначная катушка №'+(row['reel'] or 'без номера')+'. Сохраните порядок одинаковых строк и повторите загрузку.')
  else:new.append(row);continue
  row['existingId']=match['id'];used.add(match['id']);preserved+=1
  changed=[key for key in labels if row.get(key,'')!=match.get(key,'')]
  if changed:changed_rows+=1
  for key in changed:changes.append({'position':'Катушка №'+(row.get('reel') or 'не указан')+' · строка '+str(row['sourceRow']),'field':labels[key],'before':match.get(key,''),'after':row.get(key,'')})
 missing=[r for r in current if r['id'] not in used];split=0
 for parent in missing:
  # Only unnamed aggregate records may be replaced with their detailed reels.
  if parent.get('reel') not in ('','?'):raise ImportProblem('В новом файле не найдена прежняя катушка №'+parent.get('reel','')+'. Записи не удалены. Проверьте полный файл и метраж.')
  parts=[r for r in new if not r.get('parentId') and stock.product_key(r)==stock.product_key(parent)]
  if len(parts)<2 or sum(Decimal(r['length']) for r in parts)!=Decimal(str(parent['length'])):raise ImportProblem('Не удалось сверить суммарную позицию '+(parent.get('marking') or parent.get('construction') or parent['id'])+'. Проверьте состав катушек и метраж.')
  if parent['status']!='available':raise ImportProblem('Суммарная позиция находится в резерве или продана. Сначала требуется отдельная сверка.')
  for row in parts:row['parentId']=parent['id']
  split+=1
 payload['expectedVersions']={r['id']:r['version'] for r in current}
 return {'positions':len(payload['items']),'preserved':preserved,'newItems':len(new),'splitPositions':split,'metres':float(sum(Decimal(r['length']) for r in payload['items'])),'changedRows':changed_rows,'changeCount':len(changes),'changes':changes[:50]}

def preview(content,filename,kind,actor):
 if kind not in ('stock','prices'):return 400,{'error':'Выберите остатки или прайс'}
 if not isinstance(content,bytes):return 400,{'error':'Выберите Excel-файл .xlsx'}
 source=''.join(c for c in text(filename).replace('\\','/').rsplit('/',1)[-1] if ord(c)>=32)[:200]
 if not source.lower().endswith('.xlsx'):return 400,{'error':'Выберите Excel-файл .xlsx'}
 digest=hashlib.sha256(content).hexdigest()
 try:
  book,sheet=workbook(content)
  try:payload=stock_payload(sheet,source,digest) if kind=='stock' else prices_payload(sheet,source,digest)
  finally:book.close()
  with crm_store.connect() as c:
   imported=c.execute('SELECT 1 FROM warehouse_imports WHERE id=?',(digest,)).fetchone() if kind=='stock' else c.execute('SELECT 1 FROM warehouse_prices WHERE id=1 AND digest=?',(digest,)).fetchone()
  if imported:return 200,{'alreadyImported':True,'source':source,'message':'Этот файл уже загружен. Остатки, движения и прайс сохранены.'}
  if kind=='stock':summary=plan_stock(payload,stock.snapshot(True)['items']);expected=None
  else:
   previous=prices.catalogue();expected=previous['version']
   old={prices.match_key(r):Decimal(r['pricePerKm']) for r in previous['rows']}
   new_keys={prices.match_key(r) for r in payload['rows']}
   changes=[{'position':r['construction'],'field':'Цена, ₽/км с НДС','before':str(old[prices.match_key(r)]) if prices.match_key(r) in old else 'Нет цены','after':r['pricePerKm']} for r in payload['rows'] if old.get(prices.match_key(r))!=Decimal(r['pricePerKm'])]
   summary={'positions':len(payload['rows']),'changedPrices':len(changes),'previousPrices':len(previous['rows']),'removedPrices':len(old.keys()-new_keys),'changeCount':len(changes),'changes':changes[:50]}
 except ImportProblem as error:return 400,{'error':str(error)}
 except (ValueError,TypeError,KeyError,InvalidOperation):return 400,{'error':'Не удалось сверить файл. Проверьте заголовки, числа и обязательные поля.'}
 token=secrets.token_urlsafe(24);summary.update(source=source,kind=kind,expiresAt=admin_store.now()+15*60*1000)
 with crm_store.connect() as c:
  c.execute('INSERT INTO admin_import_previews VALUES(?,?,?,?,?,?,?,NULL)',(token,actor,kind,json.dumps(payload,ensure_ascii=False,default=str),json.dumps(summary,ensure_ascii=False),expected,admin_store.now()))
  # Expired unused previews contain private source data; keep only a bounded review window.
  c.execute('DELETE FROM admin_import_previews WHERE created_at<? AND result IS NULL',(admin_store.now()-24*60*60*1000,))
 return 200,{'token':token,'summary':summary,'alreadyImported':False}

def apply(body,actor):
 if not isinstance(body,dict) or body.get('confirm') is not True or not isinstance(body.get('token'),str):return 400,{'error':'Подтвердите применение проверенного файла'}
 token=body['token']
 with crm_store.connect() as c:row=c.execute('SELECT actor,kind,payload,summary,expected_price,created_at,result FROM admin_import_previews WHERE token=?',(token,)).fetchone()
 if not row or row[0]!=actor:return 404,{'error':'Предварительная сверка не найдена'}
 if row[6]:return 200,json.loads(row[6])
 if admin_store.now()-row[5]>15*60*1000:return 409,{'error':'Время сверки истекло. Загрузите файл заново.'}
 user={'login':actor,'role':'admin'};payload=json.loads(row[2])
 if row[1]=='stock':status,result=warehouse_update.apply(payload,user)
 else:status,result=prices.import_prices(payload,user,expected_version=row[4])
 if status not in (200,201):return status,result
 response={'ok':True,'summary':json.loads(row[3]),'result':result}
 with crm_store.connect() as c:
  c.execute('BEGIN IMMEDIATE');previous=c.execute('SELECT result FROM admin_import_previews WHERE token=?',(token,)).fetchone()
  if previous and previous[0]:return 200,json.loads(previous[0])
  c.execute('UPDATE admin_import_previews SET result=? WHERE token=?',(json.dumps(response,ensure_ascii=False),token))
  admin_store.record_in(c,actor,'import_'+row[1],payload['source'],'Применён файл '+('остатков' if row[1]=='stock' else 'прайса')+': '+payload['source'],json.loads(row[3]),key='import:'+token)
 return 200,response
