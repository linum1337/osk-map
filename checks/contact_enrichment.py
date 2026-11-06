import base64
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import contact_enrichment

with tempfile.TemporaryDirectory() as temp:
    os.environ.update(DATA_DIR=temp,APP_USER='admin',APP_PASSWORD='public-contacts-admin-123')
    import server,crm_store,manage_users,table_export
    original={'officeId':'office-1','name':'Fixture','city':'Test','manager':crm_store.MANAGERS[0],
              'website':'','generalPhone':'','email':'','officePhone':'leave-office-phone',
              'notes':'Manager note','status':'В работе','lat':55,'lon':37,
              'bitrixData':{'Сайт':'original CRM website','Телефон':'original CRM telephone'},
              'crmMatches':[{'id':'123','owner':'Original CRM owner','phone':'CRM phone'}]}
    blocked={**copy.deepcopy(original),'officeId':'office-2','website':'https://existing.test/'}
    with crm_store.connect() as db:
        db.execute('INSERT INTO records VALUES(?,?,1)',('office-1',json.dumps(original)))
        db.execute('INSERT INTO records VALUES(?,?,2)',('office-2',json.dumps(blocked)))
        db.execute('INSERT INTO history(record_id,changes,actor) VALUES(?,?,?)',('office-2',json.dumps({'generalPhone':''}),'manager'))
    payload={'format':'osk-public-contacts-v1','checked':'2026-11-06','records':[
        {'officeId':id,'fields':{'website':'https://official.test/','generalPhone':'+78001234567','email':'info@official.test'},
         'sources':{k:'https://official.test/contacts/' for k in ['website','generalPhone','email']}}
        for id in ['office-1','office-2']]}
    result=contact_enrichment.run(payload,crm_store.DB)
    assert result['recordsUpdated']==2 and result['fieldsFilled']=={'website':1,'generalPhone':1,'email':2}
    assert not (Path(temp)/'backups').exists(),'Preview wrote backup'
    assert crm_store.rows()[0]['website']=='','Preview changed data'
    result=contact_enrichment.run(payload,crm_store.DB,apply=True,actor='admin')
    assert Path(result['backup']).is_file()
    with sqlite3.connect(result['backup']) as db:assert json.loads(db.execute('SELECT data FROM records WHERE id="office-1"').fetchone()[0])==original
    rows={r['officeId']:r for r in crm_store.rows()}
    for key,value in original.items():
        if key not in contact_enrichment.FIELDS:assert rows['office-1'][key]==value,key
    assert rows['office-2']['website']==blocked['website'] and rows['office-2']['generalPhone']==''
    assert len(rows['office-1']['publicContactSources'])==3
    assert 'Открытые источники контактов' in table_export.csv_bytes([rows['office-1']]).decode('utf-8-sig')
    assert contact_enrichment.run(payload,crm_store.DB,apply=True)['recordsUpdated']==0,'Repeat changed data'
    illegal=copy.deepcopy(payload);illegal['records'][1]['fields']['manager']='Other'
    try:contact_enrichment.run(illegal,crm_store.DB,apply=True)
    except ValueError:pass
    else:raise AssertionError('Protected field accepted')
    assert {r['officeId']:r for r in crm_store.rows()}==rows,'Invalid payload partially changed records'
    manage_users.import_users([{'login':'Андрей Логинов','manager':crm_store.MANAGERS[0],'password':'manager-contacts-password-123'}])
    client=server.app.test_client()
    def auth(login,password):return {'Authorization':'Basic '+base64.b64encode((login+':'+password).encode()).decode()}
    admin=auth('admin',os.environ['APP_PASSWORD']);manager=auth('Андрей Логинов','manager-contacts-password-123');write={'X-Requested-With':'OSK-Map'}
    for url in ['/api/contacts/preview','/api/contacts/enrich']:
        assert client.post(url,json=payload).status_code==401
        assert client.post(url,json=payload,headers={**manager,**write}).status_code==403
        assert client.post(url,json=payload,headers=admin).status_code==403
        assert client.post(url,json=illegal,headers={**admin,**write}).status_code==400
        assert client.post(url,json=payload,headers={**admin,**write}).status_code==200
print('PASS: empty contacts only; CRM/Bitrix/manager/status/notes/coordinates preserved; manual clears protected; preview read-only; backup; idempotency; sources in export; admin-only; CSRF; invalid batch atomicity')
