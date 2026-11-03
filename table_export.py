"""Server-side administrator-only exports; every value is literal text."""
import csv,io,zipfile,xml.etree.ElementTree as E,re
TITLES=['Компания','Город','Регион','Адрес','Назначенный менеджер','Ответственный Битрикс24','Телефон из отчёта','Почта из отчёта','Карточки Битрикс24','Сайт','Телефон офиса','Общий телефон','Почта','Статус','Заметки']
def values(r):
 matches=r.get('crmMatches',[])
 def distinct(key):return '\n'.join(dict.fromkeys(str(x[key]) for x in matches if x.get(key)))
 return [r.get(k,'') for k in ['name','city','region','address','manager']]+[distinct(k) for k in ['owner','phone','email','url']]+[r.get(k,'') for k in ['website','officePhone','generalPhone','email','status','notes']]
def csv_bytes(records):
 s=io.StringIO(newline='');w=csv.writer(s,delimiter=';');w.writerow(TITLES)
 def safe(v):
  s=str(v or '')
  return "'"+s if re.match(r'^[\s]*[=+@-]',s) else s
 w.writerows([safe(v) for v in values(r)] for r in records)
 return ('\ufeff'+s.getvalue()).encode('utf-8')
def xlsx_bytes(records):
 ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main';E.register_namespace('',ns)
 def tag(n):return '{'+ns+'}'+n
 sheet=E.Element(tag('worksheet'));last=len(records)+1
 E.SubElement(sheet,tag('dimension'),ref=f'A1:O{last}')
 view=E.SubElement(E.SubElement(sheet,tag('sheetViews')),tag('sheetView'),workbookViewId='0')
 E.SubElement(view,tag('pane'),ySplit='1',topLeftCell='A2',activePane='bottomLeft',state='frozen')
 E.SubElement(sheet,tag('sheetFormatPr'),defaultRowHeight='30')
 cols=E.SubElement(sheet,tag('cols'))
 for i,width in enumerate([32,22,26,48,27,34,24,30,38,32,22,22,30,22,55],1):E.SubElement(cols,tag('col'),min=str(i),max=str(i),width=str(width),customWidth='1')
 data=E.SubElement(sheet,tag('sheetData'))
 for i,vals in enumerate([TITLES]+[values(r) for r in records],1):
  row=E.SubElement(data,tag('row'),r=str(i))
  for j,value in enumerate(vals):
   cell=E.SubElement(row,tag('c'),r=f'{chr(65+j)}{i}',t='inlineStr',s='1' if i==1 else '0')
   text=E.SubElement(E.SubElement(cell,tag('is')),tag('t'),{'{http://www.w3.org/XML/1998/namespace}space':'preserve'})
   text.text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]','',str(value or ''))[:32767]
 E.SubElement(sheet,tag('autoFilter'),ref=f'A1:O{last}')
 files={
 '[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
 '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
 'xl/workbook.xml':f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Компании" sheetId="1" r:id="rId1"/></sheets></workbook>',
 'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
 'xl/styles.xml':f'<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1959A6"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1" applyNumberFormat="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="49" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1" applyFont="1" applyFill="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
 'xl/worksheets/sheet1.xml':E.tostring(sheet,encoding='utf-8',xml_declaration=True)}
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for name,value in files.items():z.writestr(name,value)
 return out.getvalue()
