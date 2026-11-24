"""Refresh keeps reservations, sales, lineage and totals; rejects stale or partial plans."""
import os,sys,tempfile,base64,copy,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DATA_DIR=tmp,APP_USER='admin',APP_PASSWORD='fixture-admin-password')
 import server,crm_store,warehouse_store as w
 c=server.app.test_client()
 def auth(name,password):return {'Authorization':'Basic '+base64.b64encode((name+':'+password).encode()).decode(),'X-Requested-With':'OSK-Map'}
 admin=auth('admin',os.environ['APP_PASSWORD'])
 def item(row,length):return dict(sourceRow=row,pallet='1',reel=str(row),length=length,construction='ОКПД-4А-(1,5)-1/4,8',marking='fixture cable',note='',rod='1.2 ROD',location='fixture')
 original=[item(2,100),item(3,200),item(4,50)]
 assert w.import_stock(dict(format='osk-krasnodar-stock-v1',source='old.xlsx',sourceDigest='a'*64,items=original),{'login':'admin','role':'admin'})[0]==201
 first,second,parent=w.snapshot(True)['items']
 def act(r,action,**extra):return c.post('/warehouse/api/items/'+r['id']+'/action',headers=admin,json=dict(action=action,version=r['version'],requestKey='fixture-'+action+'-'+r['id']+'-'+str(r['version']),**extra))
 assert act(first,'reserve',comment='Original customer').status_code==200
 assert act(second,'sell',orderNumber='ORDER-UPDATE-42').status_code==200
 initial=w.snapshot(True);ids=[r['id'] for r in initial['items']]
 rows=[dict(original[i],existingId=ids[i],note='Corrected source note') for i in range(2)]+[dict(item(10,20),parentId=ids[2]),dict(item(11,30),parentId=ids[2])]
 body=dict(format='osk-krasnodar-stock-update-v1',source='new.xlsx',sourceDigest='b'*64,items=rows,expectedVersions={r['id']:r['version'] for r in initial['items']})
 endpoint='/warehouse/api/admin/update'
 assert c.post(endpoint,json=body).status_code==401
 w.provision({'login':'Тест Склад','password':'fixture-warehouse-password'})
 assert c.post(endpoint,headers=auth('Тест Склад','fixture-warehouse-password'),json=body).status_code==403
 for change in ['stale','length','sum','missing','duplicate']:
  bad=copy.deepcopy(body)
  if change=='stale':bad['expectedVersions'][ids[0]]=1
  elif change=='length':bad['items'][0]['length']=90
  elif change=='sum':bad['items'][-1]['length']=31
  elif change=='missing':bad['items'].pop(0)
  else:bad['items'][1]['existingId']=ids[0]
  assert c.post(endpoint,headers=admin,json=bad).status_code in (400,409),change
  assert w.snapshot(True)['items']==initial['items']
 assert act(parent,'reserve').status_code==200
 blocked=copy.deepcopy(body);blocked['expectedVersions'][ids[2]]=2
 assert c.post(endpoint,headers=admin,json=blocked).status_code==409
 reserved_parent=next(r for r in w.snapshot(True)['items'] if r['id']==ids[2]);assert act(reserved_parent,'release').status_code==200
 body['expectedVersions'][ids[2]]=3
 before=w.snapshot(True);audit=w.history()
 result=c.post(endpoint,headers=admin,json=body)
 assert result.status_code==200 and result.json['items']==4 and result.json['splitPositions']==1
 after=w.snapshot(True)
 assert after['totals']['available']==50 and after['totals']['reserved']==100 and after['totals']['sold']==200
 assert len(after['items'])==4 and sum(r['length'] for r in after['items'])==350
 assert after['items'][0]['reservedBy']==before['items'][0]['reservedBy']
 assert after['items'][1]['soldBy']==before['items'][1]['soldBy'] and after['items'][1]['soldAt']==before['items'][1]['soldAt']
 assert after['items'][1]['orderNumber']=='ORDER-UPDATE-42'
 assert all(r['id']!=ids[2] for r in after['items'])
 assert c.post(endpoint,headers=admin,json=body).json['updated'] is False
 assert w.snapshot(True)['items']==after['items']
 for child in [r for r in after['items'] if r.get('parentItemId')]:
  actions={h['action'] for h in w.history(child['id'])}
  assert {'import','reserve','release','split','import-update'}<=actions
 assert {h['id'] for h in audit}<={h['id'] for h in w.history()}
 assert act(dict(parent,version=4),'reserve').status_code==409
 assert list((Path(tmp)/'backups').glob('*.sqlite3'))
 import io,zipfile,xml.etree.ElementTree as E
 export=c.get('/warehouse/api/admin/stock.xlsx',headers=admin)
 assert export.status_code==200 and export.mimetype=='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
 with zipfile.ZipFile(io.BytesIO(export.data)) as z:
  ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
  book=E.fromstring(z.read('xl/workbook.xml'))
  assert [r.get('name') for r in book.findall('m:sheets/m:sheet',ns)]==['Состояние','Катушки','История','Архив']
  sheets=[E.fromstring(z.read('xl/worksheets/sheet'+str(i)+'.xml')) for i in [2,3,4]]
  assert len(sheets[0].findall('m:sheetData/m:row',ns))==5
  assert len(sheets[1].findall('m:sheetData/m:row',ns))==len(w.history())+1
  assert len(sheets[2].findall('m:sheetData/m:row',ns))==2
  text=E.tostring(sheets[1],encoding='unicode')
  assert 'ORDER-UPDATE-42' in text and 'Продажа' in text and 'Разбивка на катушки' in text
  assert not any(sheet.findall('.//m:f',ns) for sheet in sheets)
 assert c.get('/warehouse/api/admin/stock.xlsx',headers=auth('Тест Склад','fixture-warehouse-password')).status_code==403

 import warehouse_export
 long='😀'*17000
 binary=warehouse_export.workbook([('Тест',['Текст'],[['=1+1'],[long]])])
 with zipfile.ZipFile(io.BytesIO(binary)) as z:
  first_sheet=E.fromstring(z.read('xl/worksheets/sheet1.xml'));parts=E.fromstring(z.read('xl/worksheets/sheet2.xml'))
  assert first_sheet.find('.//m:c[@r="A2"]',ns).get('t')=='inlineStr'
  assert ''.join(r.find('m:c[@r="E'+r.get('r')+'"]/m:is/m:t',ns).text for r in parts.findall('m:sheetData/m:row',ns)[1:])==long
 print('PASS stock refresh: 136-style reel split, stable IDs, reservations/sales/order preserved, lineage and audit, stale versions, incomplete plans, length conservation, protected split, backup, idempotency, role denial')
