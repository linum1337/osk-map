"""Check deployable additions against isolated persistent supplier snapshots."""
import base64
import csv
import io
import json
import os
from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
import supplier_catalog

with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp)
    original = [
        {'id': 57, 'company_key': 'c-a-v.ru', 'name': 'VOLSIP', 'kind': 'Офис',
         'address': 'Ярославль, проспект Авиаторов, 155, помещение 32', 'lat': 57.6, 'lon': 39.9},
        {'id': 49, 'company_key': 'c-a-v.ru', 'name': 'VOLSIP', 'kind': 'Офис',
         'address': 'Москва, Боровая улица, 7', 'lat': 55.7, 'lon': 37.7},
        {'id': 10001, 'company_key': 'local.test', 'name': 'Existing local vendor',
         'address': 'Existing address', 'kind': 'Склад', 'note': 'Preserve me'},
    ]
    (folder / 'suppliers.json').write_text(json.dumps(original))
    (folder / 'networks.json').write_text(json.dumps({'c-a-v.ru': {'color': '#123456', 'corporate_color': True}}))
    before = (folder / 'suppliers.json').read_bytes()
    rows, networks = supplier_catalog.load(folder)
    assert len(rows) == len(original) + 8
    assert len({r['id'] for r in rows}) == len(rows), 'ID collision'
    assert rows[0]['kind'] == 'Производитель' and rows[1]['kind'] == 'Офис'
    assert rows[1]['manufacturer'] is True and 'Волсип' in rows[1]['aliases']
    assert rows[0]['lat'] == original[0]['lat'] and rows[0]['lon'] == original[0]['lon']
    assert rows[2] == original[2], 'Unrelated persistent data changed'
    assert networks['c-a-v.ru']['color'] == '#123456' and networks['c-a-v.ru']['point_count'] == 2
    assert networks['win-telecom.ru']['point_count'] == 2 and networks['win-telecom.ru']['is_network']
    assert networks['netron.pro']['is_network'] is False
    assert (folder / 'suppliers.json').read_bytes() == before, 'Source snapshot overwritten'
    # Deploy/reload twice must not duplicate newly persisted additions.
    (folder / 'suppliers.json').write_text(json.dumps(rows))
    again, _ = supplier_catalog.load(folder)
    assert len(again) == len(rows)
    assert list(csv.DictReader(io.StringIO(supplier_catalog.csv_text(again).lstrip('\ufeff'))))[0]['manufacturer'] == 'True'
    # The JS-only snapshots used by earlier portal packages still work.
    (folder / 'suppliers.json').unlink()
    (folder / 'data.js').write_text('const SUPPLIERS=' + json.dumps(original) + ';')
    assert len(supplier_catalog.load(folder)[0]) == len(rows)

with tempfile.TemporaryDirectory() as temp:
    os.environ.update(DATA_DIR=temp, APP_USER='admin', APP_PASSWORD='supplier-test-password-123')
    import server
    folder = Path(temp) / 'modules/suppliers'
    (folder / 'suppliers.json').write_text(json.dumps(original))
    (folder / 'networks.json').write_text('{}')
    auth = {'Authorization': 'Basic ' + base64.b64encode(b'admin:supplier-test-password-123').decode()}
    client = server.app.test_client()
    assert client.get('/suppliers/suppliers.json').status_code == 401
    rows = client.get('/suppliers/suppliers.json', headers=auth).json
    networks = client.get('/suppliers/networks.json', headers=auth).json
    data = client.get('/suppliers/data.js', headers=auth).get_data(as_text=True)
    assert json.loads(data.removeprefix('const SUPPLIERS=').removesuffix(';')) == rows
    data = client.get('/suppliers/networks.js', headers=auth).get_data(as_text=True)
    assert json.loads(data.removeprefix('const NETWORKS=').removesuffix(';')) == networks
    export = client.get('/suppliers/suppliers.csv', headers=auth)
    assert export.status_code == 200 and 'attachment' in export.headers['Content-Disposition']
    assert len(list(csv.DictReader(io.StringIO(export.data.decode('utf-8-sig'))))) == len(rows)
    assert sum(n['point_count'] for n in networks.values()) == len(rows)
    assert all(r['company_key'] in networks for r in rows)
print('PASS: existing catalogue/coordinates preserved; manufacturer office classification; safe IDs; idempotency; JS fallback; map/JSON/CSV/network consistency; authentication')
