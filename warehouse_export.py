"""Consistent full warehouse XLSX snapshot with all historical events and archived rows."""
import io,json,zipfile,xml.etree.ElementTree as E
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
import crm_store
import warehouse_store as stock
import warehouse_prices as prices
from table_export import NS,column

ACTIONS={'reserve':'Резерв','release':'Снятие резерва','sell':'Продажа','restore':'Возврат','import':'Первичный импорт','update':'Обновление из файла','split':'Разбивка на катушки','import-update':'Добавление катушки'}

def time_text(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).astimezone(ZoneInfo('Europe/Moscow')).strftime('%d.%m.%Y %H:%M:%S') if ms is not None else ''

def tables():
 with crm_store.connect() as c:
  c.execute('BEGIN')
  records=[stock.unpack(r) for r in c.execute('SELECT * FROM warehouse_items ORDER BY rowid')]
  cursor=c.execute('SELECT * FROM warehouse_history ORDER BY id');names=[x[0] for x in cursor.description];events=[dict(zip(names,r)) for r in cursor]
  catalogue=prices.catalogue(c);exported_at=stock.now_ms()
 prices.decorate({'items':records,'groups':[]},{'role':'admin','login':'export'},catalogue)
 active=[r for r in records if not r.get('supersededBy')];archived=[r for r in records if r.get('supersededBy')];by_id={r['id']:r for r in records}
 summary=[['Выгрузка (московское время)',time_text(exported_at)],['Время выгрузки UTC',datetime.fromtimestamp(exported_at/1000,timezone.utc).isoformat()],['Текущих позиций',len(active)],['Архивных суммарных позиций',len(archived)],['Событий истории',len(events)]]
 for status,label in [('available','Свободно, м'),('reserved','В резерве, м'),('sold','Продано, м')]:summary.append([label,sum(round(r['length']*1000) for r in active if r['status']==status)/1000])
 summary += [['Общий остаток (свободно + резерв), м',sum(round(r['length']*1000) for r in active if r['status']!='sold')/1000],['Метраж всех позиций, включая проданное, м',sum(round(r['length']*1000) for r in active)/1000],['Прайс',catalogue['title']],['Источник прайса',catalogue['source']],['Единица цен','Рубли за метр с НДС'],['Правило цен','Число волокон, диаметр и тип прутка'],['Состав выгрузки','Все позиции и события, независимо от фильтров и кнопки «Показать проданное». Архив не включён в текущие остатки.']]
 headers=['ID позиции','Паллет','№ катушки','Длина, м','Статус','Конструкция','Маркировка','Пруток','Примечание','Место хранения','Последнее изменение (МСК)','Изменил','Кто резервировал','Кто продал','Дата продажи (МСК)','Номер заказа покупателя','Версия','Источник','Строка источника','Исходная длина','Исходная единица','Исходная суммарная позиция','Заменена катушками','Приходная, ₽/м с НДС','+10%, ₽/м с НДС','+15%, ₽/м с НДС','+20%, ₽/м с НДС','+30%, ₽/м с НДС','Строка прайса']
 def item(r):
  return [r['id'],r.get('pallet',''),r.get('reel',''),r['length'],stock.LABELS[r['status']],*[r.get(k,'') for k in ['construction','marking','rod','note','location']],time_text(r['updatedAt']),r['updatedBy'],r.get('reservedBy'),r.get('soldBy'),time_text(r.get('soldAt')),r.get('orderNumber',''),r['version'],r.get('source'),r.get('sourceRow'),r.get('sourceLength'),r.get('sourceUnit'),r.get('parentItemId'),json.dumps(r['supersededBy'],ensure_ascii=False) if r.get('supersededBy') else '',*[Decimal(r['prices'][k]) if r.get('prices') else None for k in ['base','plus10','plus15','plus20','plus30']],r.get('priceSourceRow')]
 audit_headers=['ID события','Дата и время (МСК)','Дата и время UTC','ID позиции','№ катушки','Маркировка','Действие','Ответственный','Роль','Было','Стало','Номер заказа','Комментарий / изменения','Ключ операции','Исходная суммарная позиция','Заменена катушками']
 audit=[]
 for h in events:
  r=by_id[h['item_id']]
  audit.append([h['id'],time_text(h['created_at']),datetime.fromtimestamp(h['created_at']/1000,timezone.utc).isoformat(),h['item_id'],r.get('reel'),r.get('marking'),ACTIONS.get(h['action'],h['action']),h['actor'],h['actor_role'],stock.LABELS.get(h['from_status'],h['from_status'] or ''),stock.LABELS.get(h['to_status'],h['to_status']),h.get('order_number',''),h['comment'],h['request_key'],r.get('parentItemId'),json.dumps(r['supersededBy'],ensure_ascii=False) if r.get('supersededBy') else ''])
 return [('Состояние',['Показатель','Значение'],summary),('Катушки',headers,[item(r) for r in active]),('История',audit_headers,audit),('Архив',headers,[item(r) for r in archived])]

def xlsx_bytes():return workbook(tables())

def workbook(tables):
 # Preserve long notes and imported changes beyond Excel's per-cell limit.
 long=[]
 for title,headers,rows in tables:
  for i,row in enumerate(rows,2):
   for j,v in enumerate(row):
    if not isinstance(v,str) or len(v.encode('utf-16-le'))//2<=32000:continue
    parts=[];part='';size=0
    for char in v:
     width=2 if ord(char)>65535 else 1
     if size+width>32000:parts.append(part);part='';size=0
     part+=char;size+=width
    if part:parts.append(part)
    long.extend([[title,i,headers[j],n,s] for n,s in enumerate(parts,1)])
    row[j]=v[:150]+'… Полностью: лист «Длинные значения».'
 if long:tables.append(('Длинные значения',['Лист','Строка','Поле','Часть','Текст'],long))
 E.register_namespace('',NS)
 def tag(n):return '{'+NS+'}'+n
 files={};book=E.Element(tag('workbook'));sheets=E.SubElement(book,tag('sheets'))
 relns='http://schemas.openxmlformats.org/package/2006/relationships';relations=E.Element('Relationships',xmlns=relns)
 ct=E.Element('Types',xmlns='http://schemas.openxmlformats.org/package/2006/content-types')
 for ext,mime in [('rels','application/vnd.openxmlformats-package.relationships+xml'),('xml','application/xml')]:E.SubElement(ct,'Default',Extension=ext,ContentType=mime)
 E.SubElement(ct,'Override',PartName='/xl/workbook.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
 E.SubElement(ct,'Override',PartName='/xl/styles.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml')
 for n,(title,headers,rows) in enumerate(tables,1):
  E.SubElement(sheets,tag('sheet'),name=title,sheetId=str(n),attrib={'{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id':'rId'+str(n)})
  E.SubElement(relations,'Relationship',Id='rId'+str(n),Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet',Target=f'worksheets/sheet{n}.xml')
  E.SubElement(ct,'Override',PartName=f'/xl/worksheets/sheet{n}.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
  sheet=E.Element(tag('worksheet'));view=E.SubElement(E.SubElement(sheet,tag('sheetViews')),tag('sheetView'),workbookViewId='0')
  E.SubElement(view,tag('pane'),ySplit='1',topLeftCell='A2',activePane='bottomLeft',state='frozen')
  cols=E.SubElement(sheet,tag('cols'))
  for j,h in enumerate(headers,1):E.SubElement(cols,tag('col'),min=str(j),max=str(j),width='60' if any(x in h for x in ['Комментарий','Примечание','Значение','Маркировка','Текст']) else '28',customWidth='1')
  data=E.SubElement(sheet,tag('sheetData'))
  for i,row in enumerate([headers]+rows,1):
   height=42 if i==1 else min(120,max(30,15*max((str(v).count('\n')+1 for v in row),default=1)))
   line=E.SubElement(data,tag('row'),r=str(i),ht=str(height),customHeight='1')
   for j,v in enumerate(row):
    numeric=isinstance(v,(int,float,Decimal)) and not isinstance(v,bool)
    cell=E.SubElement(line,tag('c'),r=column(j)+str(i),s='1' if i==1 else '2' if isinstance(v,Decimal) else '0')
    if numeric:E.SubElement(cell,tag('v')).text=str(v)
    else:
     cell.set('t','inlineStr');text=E.SubElement(E.SubElement(cell,tag('is')),tag('t'));text.set('{http://www.w3.org/XML/1998/namespace}space','preserve');text.text=''.join(c for c in str(v if v is not None else '') if c in '\t\n\r' or ord(c)>=32)
  E.SubElement(sheet,tag('autoFilter'),ref=f'A1:{column(len(headers)-1)}{len(rows)+1}')
  files[f'xl/worksheets/sheet{n}.xml']=E.tostring(sheet,encoding='utf-8',xml_declaration=True)
 E.SubElement(relations,'Relationship',Id='styles',Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles',Target='styles.xml')
 from warehouse_price_export import xlsx_bytes as price_book
 with zipfile.ZipFile(io.BytesIO(price_book({'title':'','source':'','rows':[]}))) as z:files['xl/styles.xml']=z.read('xl/styles.xml')
 files.update({'[Content_Types].xml':E.tostring(ct,encoding='utf-8',xml_declaration=True),'xl/workbook.xml':E.tostring(book,encoding='utf-8',xml_declaration=True),'xl/_rels/workbook.xml.rels':E.tostring(relations,encoding='utf-8',xml_declaration=True),'_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'})
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for name,data in files.items():z.writestr(name,data)
 return out.getvalue()
