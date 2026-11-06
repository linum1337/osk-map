"""Fill only empty public contact fields; keep CRM and manager data unchanged."""
import copy
import datetime
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

FIELDS = {'website', 'generalPhone', 'email'}


def valid_url(value):
    if not isinstance(value, str) or not value or len(value) > 2000 or any(c.isspace() for c in value):
        return False
    try:
        url = urlsplit(value)
        return url.scheme in ('http', 'https') and bool(url.hostname) and not url.username and not url.password
    except ValueError:
        return False


def validate(payload):
    if not isinstance(payload, dict) or payload.get('format') != 'osk-public-contacts-v1':
        raise ValueError('Неверный формат дополнения контактов')
    date = payload.get('checked')
    if not isinstance(date, str) or datetime.date.fromisoformat(date).isoformat() != date:
        raise ValueError('Укажите дату проверки')
    rows = payload.get('records')
    if not isinstance(rows, list) or not rows or len(rows) > 5000:
        raise ValueError('Нужно от 1 до 5000 записей')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'officeId', 'fields', 'sources'}:
            raise ValueError('Допустимы только ID, контакты и источники')
        id = row.get('officeId')
        if not isinstance(id, str) or not re.fullmatch(r'office-\d+', id) or id in seen:
            raise ValueError('Неверный или повторный ID')
        seen.add(id)
        fields, sources = row.get('fields'), row.get('sources')
        if not isinstance(fields, dict) or not fields or set(fields) - FIELDS:
            raise ValueError('Разрешены только сайт, общий телефон и почта')
        if not isinstance(sources, dict) or set(sources) != set(fields):
            raise ValueError('Для каждого поля нужен источник')
        for key, value in fields.items():
            if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 2000:
                raise ValueError('Неверное значение контакта')
            if not valid_url(sources[key]):
                raise ValueError('Нужна ссылка на открытый источник')
            if key == 'website' and not valid_url(value):
                raise ValueError('Неверный адрес сайта')
            if key == 'email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
                raise ValueError('Неверная почта')
            if key == 'generalPhone' and not re.fullmatch(r'\+?[\d ()-]{7,80}', value):
                raise ValueError('Неверный телефон')
    return rows, date


def run(payload, db, apply=False, actor=''):
    entries, checked = validate(payload)
    db = Path(db).resolve()
    if not db.is_file():
        raise ValueError('Рабочая база не найдена')
    summary = {'recordsRequested': len(entries), 'recordsUpdated': 0, 'fieldsFilled': {},
               'nonemptySkipped': 0, 'manuallyClearedSkipped': 0, 'missingRecords': 0}
    backup = None
    if apply:
        directory = db.parent / 'backups'
        directory.mkdir(exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        backup = directory / ('before-public-contacts-' + stamp + '.sqlite3')
        with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(backup) as target:
            source.backup(target)
    with sqlite3.connect(db.as_uri() + ('?mode=rw' if apply else '?mode=ro'), uri=True, timeout=30) as c:
        c.execute('BEGIN IMMEDIATE' if apply else 'BEGIN')
        for entry in entries:
            id = entry['officeId']
            row = c.execute('SELECT data,version FROM records WHERE id=?', (id,)).fetchone()
            if not row:
                summary['missingRecords'] += 1
                continue
            current = json.loads(row[0])
            changes = {}
            cleared = set()
            for raw, editor in c.execute('SELECT changes,actor FROM history WHERE record_id=? ORDER BY id', (id,)):
                history = json.loads(raw)
                if editor and not editor.startswith(('Импорт ', 'Открытые контакты:')):
                    for key in FIELDS.intersection(history):
                        if not history[key]:cleared.add(key)
                        else:cleared.discard(key)
            provenance = copy.deepcopy(current.get('publicContactSources') or [])
            for key, value in entry['fields'].items():
                if current.get(key):
                    summary['nonemptySkipped'] += 1
                    continue
                if key in cleared:
                    summary['manuallyClearedSkipped'] += 1
                    continue
                changes[key] = value
                summary['fieldsFilled'][key] = summary['fieldsFilled'].get(key, 0) + 1
                provenance.append({'field': key, 'value': value, 'url': entry['sources'][key], 'checked': checked})
            if not changes:
                continue
            changes['publicContactSources'] = provenance
            summary['recordsUpdated'] += 1
            if apply:
                current.update(changes)
                c.execute('UPDATE records SET data=?,version=version+1 WHERE id=?', (json.dumps(current, ensure_ascii=False), id))
                c.execute('INSERT INTO history(record_id,changes,actor) VALUES(?,?,?)',
                          (id, json.dumps(changes, ensure_ascii=False), 'Открытые контакты: ' + actor))
        if apply:c.commit()
        else:c.rollback()
    if backup:summary['backup'] = str(backup)
    return summary
