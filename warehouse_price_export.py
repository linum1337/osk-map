"""Numeric XLSX export of the full private warehouse price catalogue."""
import io
import zipfile
import xml.etree.ElementTree as E
from decimal import Decimal
from table_export import NS,column

def xlsx_bytes(catalogue):
 headers=['Маркировка','Пруток','Исходная цена, ₽/км с НДС','Приходная, ₽/м с НДС','+10%, ₽/м с НДС','+15%, ₽/м с НДС','+20%, ₽/м с НДС','+30%, ₽/м с НДС']
 E.register_namespace('',NS)
 def tag(n):return '{'+NS+'}'+n
 sheet=E.Element(tag('worksheet'))
 view=E.SubElement(E.SubElement(sheet,tag('sheetViews')),tag('sheetView'),workbookViewId='0')
 E.SubElement(view,tag('pane'),ySplit='3',topLeftCell='A4',activePane='bottomLeft',state='frozen')
 cols=E.SubElement(sheet,tag('cols'))
 for i in range(1,len(headers)+1):E.SubElement(cols,tag('col'),min=str(i),max=str(i),width='36' if i==1 else '25' if i==2 else '22',customWidth='1')
 data=E.SubElement(sheet,tag('sheetData'))
 def row(number,values,heading=False):
  r=E.SubElement(data,tag('row'),r=str(number),ht='36' if heading else '28',customHeight='1')
  for i,value in enumerate(values):
   cell=E.SubElement(r,tag('c'),r=column(i)+str(number),s='1' if heading else '2' if isinstance(value,Decimal) else '0')
   if isinstance(value,Decimal):E.SubElement(cell,tag('v')).text=format(value,'f')
   else:
    cell.set('t','inlineStr');t=E.SubElement(E.SubElement(cell,tag('is')),tag('t'));t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');t.text=''.join(c for c in str(value) if c in '\t\n\r' or ord(c)>=32)
 row(1,[catalogue['title']],True)
 row(2,['Источник: '+catalogue['source']])
 row(3,headers,True)
 for i,r in enumerate(catalogue['rows'],4):
  row(i,[r.get('marking') or r['construction'],r['category']]+[Decimal(r['pricePerKm'])]+[Decimal(r['prices'][k]) for k in ['base','plus10','plus15','plus20','plus30']])
 E.SubElement(sheet,tag('autoFilter'),ref='A3:H'+str(len(catalogue['rows'])+3))
 E.SubElement(sheet,tag('mergeCells'),count='2').extend([E.Element(tag('mergeCell'),ref='A1:H1'),E.Element(tag('mergeCell'),ref='A2:H2')])
 styles=f'''<styleSheet xmlns="{NS}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1959A6"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
 files={'xl/worksheets/sheet1.xml':E.tostring(sheet,encoding='utf-8',xml_declaration=True),'xl/styles.xml':styles,
 '[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
 '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
 'xl/workbook.xml':f'<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Прайс" sheetId="1" r:id="rId1"/></sheets></workbook>',
 'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'}
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for name,value in files.items():z.writestr(name,value)
 return out.getvalue()
