"""Private, self-contained application backup with consistent SQLite snapshot."""
import hashlib,io,json,os,re,sqlite3,tarfile,tempfile
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parent
INSTRUCTIONS='''ВОССТАНОВЛЕНИЕ ПОРТАЛА ОСК НА ДРУГОМ СЕРВЕРЕ

1. Нужны Docker Engine, Docker Compose v2, Python 3.11+ и доступные порты 80/443.
   Сборка загружает Python-образ, Caddy и закреплённые зависимости из интернета.
2. Распакуйте архив в отдельный закрытый каталог. Он содержит рабочую базу и доступы.
   tar -xzf osk-site-backup-<дата>.tar.gz
   cd osk-portal
3. ДО ПЕРВОГО ЗАПУСКА проверьте целостность:
   python3 verify_restore.py
4. В файле .env измените только DOMAIN на домен нового сервера.
   Направьте DNS этого домена на новый сервер. Старый сайт архив не изменяет.
5. Запустите именно файл переноса:
   docker compose -f compose.restore.yaml up -d --build
   docker compose -f compose.restore.yaml ps
6. Откройте https://<новый-домен>/login и войдите существующей учётной записью.
   Проверьте компании, карты ТК и поставщиков, склад, историю, резерв и продажу.
   Администратор и все остальные пароли сохранены. Настройки администратора
   находятся в data/runtime-settings.json, остальные учётки и хеши — в SQLite.
   Ключ сессий сохранён в data/session.key. Кэш тайлов заново загрузится из сети.
7. Данные хранятся в ./data. Не удаляйте этот каталог при обновлении.
   Не накладывайте копию на уже работающую базу и не удаляйте исходный архив.

СОСТАВ
Код и ресурсы сайта, текущая SQLite со всеми таблицами и историей, учётные записи,
прайс и склад, настройки видимости карт, данные ТК/поставщиков, настройки запуска,
сохранённые доступы администратора и ключ сессий. BACKUP-MANIFEST.json содержит
контрольные суммы файлов и число строк таблиц.

ОСОБЕННОСТИ ПЕРЕНОСА
Архив сайта не является образом операционной системы. Кэш карт, старые резервные
копии, SSL-сертификаты, настройки старого Traefik и SSH-ключи CI/CD не включены.
Для нового домена Caddy получает сертификат автоматически. CI/CD при необходимости
настраивается отдельно на новый сервер. Исходный production-хост не меняется.
'''

def build_backup(db_path,admin_user,admin_password,domain,root=ROOT):
 root=Path(root).resolve();db_path=Path(db_path).resolve();data_dir=db_path.parent
 if not isinstance(admin_user,str) or not admin_user or not isinstance(admin_password,str) or len(admin_password)<16:raise ValueError('Invalid backup administrator settings')
 if not isinstance(domain,str) or not re.fullmatch(r'[a-zA-Z0-9.-]+(?::[0-9]+)?',domain):raise ValueError('Invalid backup domain')
 output=tempfile.SpooledTemporaryFile(max_size=8*1024*1024,mode='w+b');manifest={'format':'osk-site-backup-v1','createdAt':datetime.now(timezone.utc).isoformat(),'files':{},'tables':{},'omitted':['tile cache','old backup copies','host TLS and SSH configuration']}
 try:
  with tempfile.TemporaryDirectory(prefix='osk-site-backup-') as temp:
   snapshot=Path(temp)/'crm.sqlite3'
   with sqlite3.connect(db_path.as_uri()+'?mode=ro',uri=True,timeout=30) as source,sqlite3.connect(snapshot) as target:
    source.backup(target,pages=256,sleep=.01)
    target.execute('PRAGMA journal_mode=DELETE')
    if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database integrity check failed')
    for table, in target.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
     quoted='"'+table.replace('"','""')+'"';manifest['tables'][table]=target.execute('SELECT COUNT(*) FROM '+quoted).fetchone()[0]
   with tarfile.open(fileobj=output,mode='w:gz',compresslevel=6) as archive:
    def add_bytes(name,content,mode=0o600,record=True):
     if name in manifest['files']:raise ValueError('Duplicate backup member')
     content=content.encode('utf-8') if isinstance(content,str) else content
     info=tarfile.TarInfo('osk-portal/'+name);info.size=len(content);info.mode=mode
     archive.addfile(info,io.BytesIO(content))
     if record:manifest['files'][name]={'size':len(content),'sha256':hashlib.sha256(content).hexdigest()}
    def add_file(name,path):
     if path.is_symlink() or not path.is_file():raise ValueError('Unsafe backup file')
     add_bytes(name,path.read_bytes())
    for path in sorted(root.glob('*.py')):add_file(path.name,path)
    for name in ['competitor_sources.json','competitor_presence.json','competitor_regions.json','requirements.txt','Dockerfile','.dockerignore','compose.yaml','compose.restore.yaml','Caddyfile','README.md']:
     add_file(name,root/name)
    for directory in ['app','modules']:
     for path in sorted((root/directory).rglob('*')):
      if path.is_symlink():raise ValueError('Symlink in application resources')
      if path.is_file() and '__pycache__' not in path.parts:add_file(path.relative_to(root).as_posix(),path)
    for path in sorted((data_dir/'modules').rglob('*')):
     if path.is_symlink():raise ValueError('Symlink in module data')
     if path.is_file():add_file('data/modules/'+path.relative_to(data_dir/'modules').as_posix(),path)
    add_file('data/crm.sqlite3',snapshot)
    add_file('data/session.key',data_dir/'session.key')
    add_bytes('data/runtime-settings.json',json.dumps({'APP_USER':admin_user,'APP_PASSWORD':admin_password},ensure_ascii=False,indent=2))
    add_bytes('.env','DOMAIN='+domain+'\n')
    add_bytes('ВОССТАНОВЛЕНИЕ.txt',INSTRUCTIONS)
    add_bytes('BACKUP-MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2),record=False)
  output.seek(0);return output
 except BaseException:
  output.close();raise
