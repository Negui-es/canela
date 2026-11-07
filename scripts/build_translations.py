"""Compile checked-in gettext catalogs without a system gettext installation."""
from pathlib import Path
import re
import polib

ROOT = Path(__file__).resolve().parent.parent


def compile_catalogs():
    count = 0
    for path in sorted((ROOT / 'locale').glob('*/LC_MESSAGES/*.po')):
        catalog = polib.pofile(str(path))
        for entry in catalog:
            if entry.obsolete:
                continue
            translations = list(entry.msgstr_plural.values()) if entry.msgid_plural else [entry.msgstr]
            if entry.fuzzy or not translations or any(not text for text in translations):
                raise ValueError(f'Incomplete translation: {path}: {entry.msgid}')
            placeholders = set(re.findall(r'%\([^)]+\)[sd]', entry.msgid))
            if any(set(re.findall(r'%\([^)]+\)[sd]', text)) != placeholders for text in translations):
                raise ValueError(f'Invalid placeholders: {path}: {entry.msgid}')
            if entry.msgctxt == 'URL':
                converters = sorted(re.findall(r'<[^>]+>', entry.msgid))
                if (sorted(re.findall(r'<[^>]+>', entry.msgstr)) != converters
                        or not entry.msgstr.isascii() or entry.msgstr.startswith('/')
                        or not entry.msgstr.endswith('/') or any(c in entry.msgstr for c in '?#')):
                    raise ValueError(f'Invalid translated URL: {path}: {entry.msgid}')
        catalog.save_as_mofile(str(path.with_suffix('.mo')))
        count += 1
    if count != 10:
        raise ValueError(f'Expected 10 catalogs, found {count}')
    return count


if __name__ == '__main__':
    print(f'{compile_catalogs()} translation catalogs compiled.')
