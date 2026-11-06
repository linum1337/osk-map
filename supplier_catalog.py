"""Overlay reviewed public supplier facts on persistent private module snapshots.

The original files stay untouched. Map data, network counts and CSV are generated
from the same merged catalogue, so source deployments can ship additions safely.
"""
import copy
import csv
import io
import json
import re
from collections import Counter
from pathlib import Path


def read_value(folder, json_name, js_name, variable, default):
    path = folder / json_name
    if path.is_file():
        return json.loads(path.read_text(encoding='utf-8-sig'))
    path = folder / js_name
    if path.is_file():
        script = path.read_text(encoding='utf-8-sig')
        match = re.fullmatch(r'\s*(?:const|let|var)\s+' + re.escape(variable)
                             + r'\s*=\s*(.*?)\s*;?\s*', script, re.S)
        if not match:
            raise ValueError('Invalid supplier snapshot: ' + js_name)
        return json.loads(match[1])
    return copy.deepcopy(default)


def point_key(row):
    # A physical point is unique by company and address, not by display name.
    return (row.get('company_key'), re.sub(r'\W+', '', row.get('address', '').casefold()))


def load(folder, additions_file=None):
    folder = Path(folder)
    rows = read_value(folder, 'suppliers.json', 'data.js', 'SUPPLIERS', [])
    networks = read_value(folder, 'networks.json', 'networks.js', 'NETWORKS', {})
    if not isinstance(rows, list) or not isinstance(networks, dict):
        raise ValueError('Invalid supplier catalogue')
    additions_file = additions_file or Path(__file__).parent / 'modules/suppliers/catalog-additions.json'
    review = json.loads(Path(additions_file).read_text())
    present = {point_key(r) for r in rows}
    ids = {r['id'] for r in rows if 'id' in r}
    for row in review.get('additions', []):
        identity = point_key(row)
        if identity in present:
            continue
        row = copy.deepcopy(row)
        # Do not let an independently added persistent point share a marker ID.
        if row['id'] in ids:
            row['id'] = max((i for i in ids if isinstance(i, int)), default=10000) + 1
        ids.add(row['id'])
        rows.append(row)
        present.add(identity)
    for row in rows:
        row.update(copy.deepcopy(review.get('company_updates', {}).get(row.get('company_key'), {})))
        for patch in review.get('point_updates', []):
            if (row.get('company_key') == patch['company_key']
                    and all(s.casefold() in row.get('address', '').casefold()
                            for s in patch['address_contains'])):
                row.update(copy.deepcopy(patch['changes']))
    counts = Counter(r.get('company_key') for r in rows if r.get('company_key'))
    result = {}
    for row in rows:
        key = row.get('company_key')
        if not key or key in result:
            continue
        network = copy.deepcopy(networks.get(key, {}))
        network.update(id=key, name=row['name'], point_count=counts[key], is_network=counts[key] > 1)
        network.setdefault('color', '#647b86')
        network.setdefault('corporate_color', False)
        network.setdefault('color_source', None)
        network.setdefault('color_method', 'Условный цвет')
        result[key] = network
    return rows, result


def csv_text(rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        values = {}
        for key in fields:
            value = row.get(key, '')
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            # Prevent spreadsheet formulas from untrusted persistent text.
            if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r')):
                value = "'" + value
            values[key] = value
        writer.writerow(values)
    return '\ufeff' + out.getvalue()
