"""Creates a portable data + media backup, without changing the application."""
import os
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

root=Path(__file__).resolve().parent.parent
os.environ.setdefault('DJANGO_SETTINGS_MODULE','canela.settings')
target_dir=root/'backups'
target_dir.mkdir(exist_ok=True)
data_dir=root/'data'
data_dir.mkdir(exist_ok=True)
target=target_dir/('canela-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'.zip')
with tempfile.TemporaryDirectory(dir=data_dir) as temporary:
    temporary_path=Path(temporary).resolve()
    assert temporary_path.is_relative_to(data_dir.resolve())
    dump=temporary_path/'database.json'
    with dump.open('wb') as output:
        subprocess.run([sys.executable,str(root/'manage.py'),'dumpdata','--natural-foreign','--natural-primary',
                        '--exclude=contenttypes','--exclude=auth.permission','--exclude=sessions','--exclude=admin.logentry'],
                       cwd=root,stdout=output,check=True)
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(dump,'database.json')
        for photo in (root/'media').rglob('*'):
            if photo.is_file():
                archive.write(photo,photo.relative_to(root))
print(f'Copia guardada: {target}')
