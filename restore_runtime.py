"""Load preserved administrator settings without putting them into an image."""
import json,os
from pathlib import Path

def load_settings():
 data=json.loads((Path(os.environ.get('DATA_DIR','data'))/'runtime-settings.json').read_text())
 if not isinstance(data.get('APP_USER'),str) or not data['APP_USER'] or not isinstance(data.get('APP_PASSWORD'),str) or len(data['APP_PASSWORD'])<16:raise RuntimeError('Invalid restored administrator configuration')
 return {k:data[k] for k in ['APP_USER','APP_PASSWORD']}

if __name__=='__main__':
 os.environ.update(load_settings())
 os.execvp('gunicorn',['gunicorn','--bind','0.0.0.0:8000','--workers','1','--threads','8','--timeout','90','--access-logfile','-','server:app'])
