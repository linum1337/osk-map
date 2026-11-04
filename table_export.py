"""Full administrator export: current records and the recorded edit history."""
import csv,io,zipfile,xml.etree.ElementTree as E,re,json
NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
TITLES=['Компания','Город','Регион','Адрес','Назначенный менеджер','Ответственный Битрикс24','Телефон из отчёта','Почта из отчёта','Карточки Битрикс24','Сайт','Телефон офиса','Общий телефон','Почта','Статус','Заметки']
BASE_FIELDS={'name','city','region','address','manager','website','officePhone','generalPhone','email','status','notes'}
LABELS={'bitrixData':'Все поля Битрикс24 (JSON)','bitrixReportDate':'Дата выгрузки Битрикс24','bitrixSource':'Источник Битрикс24','bitrixDescription':'Описание Битрикс24','bitrixLastComment':'Последний комментарий Битрикс24','bitrixCommentDate':'Дата комментария Битрикс24','bitrixCommentAuthor':'Автор комментария Битрикс24','bitrixIndustry':'Отрасль Битрикс24','bitrixStatus':'Статус Битрикс24','bitrixProducts':'Продукты Битрикс24','bitrixCities':'Города Битрикс24','crmPreviousMatches':'Предыдущие сведения Битрикс24 (JSON)','sourceOfficeId':'Исходный ID клиента','requestNumber':'Номер запроса','requestComment':'Комментарий для головного офиса','requestAuthor':'Автор запроса','requestCreatedAt':'Дата запроса (UTC)','requestStatus':'Статус запроса','officeId':'ID записи','id':'ID компании','slug':'Код бренда','services':'Виды услуг','extraServices':'Дополнительные услуги','group':'Группа компаний','district':'Федеральный округ','source':'Источник адреса','sources':'Источники','sourceType':'Тип источника','catalogSource':'Источник каталога','officeType':'Тип офиса','phone':'Телефон исходного источника','lat':'Широта','lon':'Долгота','geoSource':'Источник координат','precision':'Точность координат','addressStatus':'Статус адреса','visitNote':'Примечание о посещении','orgId':'ID организации','office':'Адресная точка','checked':'Дата проверки','recordId':'Исходный ID записи','key':'Ключ записи','local':'Местная компания','contactSources':'Источники контактов','hasContact':'Контакты найдены','crmMatches':'Совпадения Битрикс24 — все данные (JSON)','crmCheck':'Статус сверки Битрикс24','crmReportPeriod':'Период отчёта Битрикс24','providerPresenceSources':'Источники присутствия','population2021':'Население, 2021','populationSource':'Источник населения','yandexSource':'Источник Яндекс','officialSource':'Официальный источник','geocoderLabel':'Результат геокодирования','fromBitrix':'Компания из Битрикс24','citiesFromName':'Города из названия','citySource':'Источник города','hiddenReason':'Причина скрытия','brandName':'Название бренда','presenceEvidence':'Подтверждение присутствия','settlementId':'ID населённого пункта','version':'Версия записи','lastEditedAt':'Последнее изменение (UTC)','lastEditedBy':'Автор последнего изменения'}
def text(v):
 if v is None:return ''
 if isinstance(v,(list,dict,bool)):return json.dumps(v,ensure_ascii=False)
 return str(v)
def values(r):
 matches=r.get('crmMatches',[])
 def distinct(key):return '\n'.join(dict.fromkeys(str(x[key]) for x in matches if x.get(key)))
 return [r.get(k,'') for k in ['name','city','region','address','manager']]+[distinct(k) for k in ['owner','phone','email','url']]+[r.get(k,'') for k in ['website','officePhone','generalPhone','email','status','notes']]
def company_table(records):
 extra=sorted({k for r in records for k in r}-BASE_FIELDS)
 return TITLES+[LABELS.get(k,k) for k in extra],[[*values(r),*[r.get(k) for k in extra]] for r in records]
def csv_bytes(records):
 titles,rows=company_table(records);s=io.StringIO(newline='');w=csv.writer(s,delimiter=';');w.writerow(titles)
 def safe(v):
  value=text(v)
  return "'"+value if re.match(r'^[\s]*[=+@-]',value) else value
 w.writerows([safe(v) for v in row] for row in rows)
 return ('\ufeff'+s.getvalue()).encode('utf-8')
def column(index):
 out='';index+=1
 while index:index,n=divmod(index-1,26);out=chr(65+n)+out
 return out
STYLES='<styleSheet xmlns="{NS}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1959A6"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1" applyNumberFormat="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="49" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1" applyFont="1" applyFill="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
def xlsx_bytes(records,history=None):
 titles,rows=company_table(records)
 audit_titles=['ID изменения','ID записи','Компания','Дата изменения (UTC)','Кто внёс изменение','Назначенный менеджер','Сайт','Телефон офиса','Общий телефон','Почта','Статус','Заметки','Все внесённые поля (JSON)']
 names={r['officeId']:r.get('name','') for r in records}
 audit=[]
 for h in history or []:
  changes=h.get('changes',{})
  audit.append([h.get('id'),h.get('recordId'),names.get(h.get('recordId'),''),h.get('changedAt'),h.get('actor') or 'Не зафиксирован (старое изменение)',*[changes.get(k) for k in ['manager','website','officePhone','generalPhone','email','status','notes']],changes])
 tables=[('Компании',titles,rows),('Изменения',audit_titles,audit)]
 # Excel cells support at most 32767 UTF-16 units. Keep oversized values in numbered parts.
 long_rows=[]
 def chunks(value):
  chunk=[];size=0
  for char in value:
   width=2 if ord(char)>65535 else 1
   if size+width>32000:yield ''.join(chunk);chunk=[];size=0
   chunk.append(char);size+=width
  if chunk:yield ''.join(chunk)
 for name,headers,data in tables:
  for i,row in enumerate(data,2):
   for j,value in enumerate(row):
    value=text(value)
    if len(value.encode('utf-16-le',errors='replace'))//2>32767:
     for part,chunk in enumerate(chunks(value),1):long_rows.append([name,i,headers[j],part,chunk])
     row[j]=value[:200]+'… Полное значение — лист «Длинные значения», строка '+str(i)+', поле «'+headers[j]+'»'
 if long_rows:tables.append(('Длинные значения',['Лист','Строка Excel','Поле','Номер части','Текст значения'],long_rows))
 E.register_namespace('',NS)
 def tag(n):return '{'+NS+'}'+n
 files={}
 for sheet_id,(name,headers,data) in enumerate(tables,1):
  sheet=E.Element(tag('worksheet'));last=len(data)+1;lastcol=column(len(headers)-1)
  E.SubElement(sheet,tag('dimension'),ref=f'A1:{lastcol}{last}')
  view=E.SubElement(E.SubElement(sheet,tag('sheetViews')),tag('sheetView'),workbookViewId='0')
  E.SubElement(view,tag('pane'),ySplit='1',topLeftCell='A2',activePane='bottomLeft',state='frozen')
  E.SubElement(sheet,tag('sheetFormatPr'),defaultRowHeight='30');cols=E.SubElement(sheet,tag('cols'))
  for j,title in enumerate(headers,1):E.SubElement(cols,tag('col'),min=str(j),max=str(j),width='55' if 'Заметки' in title or 'JSON' in title or title=='Текст значения' else '28',customWidth='1')
  sheet_data=E.SubElement(sheet,tag('sheetData'))
  for i,vals in enumerate([headers]+data,1):
   row=E.SubElement(sheet_data,tag('row'),r=str(i))
   for j,value in enumerate(vals):
    cell=E.SubElement(row,tag('c'),r=f'{column(j)}{i}',t='inlineStr',s='1' if i==1 else '0')
    node=E.SubElement(E.SubElement(cell,tag('is')),tag('t'),{'{http://www.w3.org/XML/1998/namespace}space':'preserve'})
    node.text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]','',text(value))
  E.SubElement(sheet,tag('autoFilter'),ref=f'A1:{lastcol}{last}')
  files[f'xl/worksheets/sheet{sheet_id}.xml']=E.tostring(sheet,encoding='utf-8',xml_declaration=True)
 relns='http://schemas.openxmlformats.org/package/2006/relationships';docrel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
 content_ns='http://schemas.openxmlformats.org/package/2006/content-types';types=E.Element('Types',xmlns=content_ns)
 E.SubElement(types,'Default',Extension='rels',ContentType='application/vnd.openxmlformats-package.relationships+xml');E.SubElement(types,'Default',Extension='xml',ContentType='application/xml')
 for path,kind in [('workbook.xml','sheet.main'),('styles.xml','styles')]:E.SubElement(types,'Override',PartName='/xl/'+path,ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.'+kind+'+xml')
 workbook=E.Element(tag('workbook'),{'xmlns:r':docrel});sheets=E.SubElement(workbook,tag('sheets'));rels=E.Element('Relationships',xmlns=relns)
 for i,(name,_,_) in enumerate(tables,1):
  E.SubElement(sheets,tag('sheet'),name=name,sheetId=str(i),attrib={'r:id':'rId'+str(i)})
  E.SubElement(rels,'Relationship',Id='rId'+str(i),Type=docrel+'/worksheet',Target=f'worksheets/sheet{i}.xml')
  E.SubElement(types,'Override',PartName=f'/xl/worksheets/sheet{i}.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
 E.SubElement(rels,'Relationship',Id='rIdStyles',Type=docrel+'/styles',Target='styles.xml')
 files.update({'[Content_Types].xml':E.tostring(types,encoding='utf-8'),'_rels/.rels':f'<Relationships xmlns="{relns}"><Relationship Id="rId1" Type="{docrel}/officeDocument" Target="xl/workbook.xml"/></Relationships>','xl/workbook.xml':E.tostring(workbook,encoding='utf-8'),'xl/_rels/workbook.xml.rels':E.tostring(rels,encoding='utf-8'),'xl/styles.xml':STYLES.replace('{NS}',NS)})
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for name,value in files.items():z.writestr(name,value)
 return out.getvalue()
