"""Run inside app container: python backup.py > backup.sqlite3"""
import os,sqlite3,tempfile,sys
from pathlib import Path
source=Path(os.environ.get('DATA_DIR','data'))/'crm.sqlite3'
if not source.is_file():raise SystemExit('Database not found')
with tempfile.TemporaryDirectory() as d:
 dest=Path(d)/'backup.sqlite3'
 with sqlite3.connect(source) as a,sqlite3.connect(dest) as b:a.backup(b)
 with dest.open('rb') as f:
  while chunk:=f.read(1024*1024):sys.stdout.buffer.write(chunk)
