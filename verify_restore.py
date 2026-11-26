"""Verify a freshly extracted private backup before starting the application."""
import hashlib,json,sqlite3
from pathlib import Path

def verify(root):
 root=Path(root).resolve();manifest=json.loads((root/'BACKUP-MANIFEST.json').read_text())
 if manifest.get('format')!='osk-site-backup-v1':raise ValueError('Unknown backup format')
 for name,expected in manifest['files'].items():
  path=(root/name).resolve()
  if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():raise ValueError('Missing or unsafe backup member: '+name)
  with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
  if digest!=expected['sha256'] or path.stat().st_size!=expected['size']:raise ValueError('Backup checksum mismatch: '+name)
 with sqlite3.connect((root/'data/crm.sqlite3').as_uri()+'?mode=ro&immutable=1',uri=True) as db:
  if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database integrity check failed')
  for table,count in manifest['tables'].items():
   quoted='"'+table.replace('"','""')+'"'
   if db.execute('SELECT COUNT(*) FROM '+quoted).fetchone()[0]!=count:raise ValueError('Database count mismatch: '+table)
 settings=json.loads((root/'data/runtime-settings.json').read_text())
 if not isinstance(settings.get('APP_PASSWORD'),str) or len(settings['APP_PASSWORD'])<16:raise ValueError('Administrator settings are incomplete')
 if not (root/'data/session.key').read_text().strip():raise ValueError('Session key is missing')
 return {'files':len(manifest['files']),'tables':manifest['tables'],'createdAt':manifest['createdAt']}

if __name__=='__main__':
 result=verify(Path(__file__).resolve().parent)
 print('Backup verified:',result['files'],'files;',len(result['tables']),'database tables; created',result['createdAt'])
