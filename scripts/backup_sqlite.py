"""Native SQLite + media snapshot, usable before applying schema migrations."""
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

root=Path(__file__).resolve().parent.parent
database=root/'data'/'canela.sqlite3'
if not database.is_file():
    raise SystemExit('No se encontró la base local de Canela.')
target_dir=root/'backups'
target_dir.mkdir(exist_ok=True)
target=target_dir/('canela-sqlite-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'.zip')
with tempfile.TemporaryDirectory(dir=root/'data') as temporary:
    temporary_path=Path(temporary).resolve()
    assert temporary_path.is_relative_to((root/'data').resolve())
    snapshot=temporary_path/'canela.sqlite3'
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as source, closing(sqlite3.connect(snapshot)) as destination:
        source.backup(destination)
        assert destination.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(snapshot,'data/canela.sqlite3')
        media=root/'media'
        for file in media.rglob('*'):
            if file.is_file():
                assert file.resolve().is_relative_to(media.resolve())
                archive.write(file,file.relative_to(root))
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
print(f'Copia nativa guardada y comprobada: {target}')
