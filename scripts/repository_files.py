"""Publishable source boundary shared by the audit and initial publication."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'.gitignore', '.dockerignore', '.env.example', 'compose.yaml', 'Dockerfile',
              'manage.py', 'requirements.txt', 'run_local.py', 'Iniciar Canela.cmd',
              'package.json', 'pnpm-lock.yaml', 'pnpm-workspace.yaml', 'README.md',
              'LICENSE', 'THIRD_PARTY_NOTICES.md'}
SUFFIXES = {'canela': {'.py'}, 'studio': {'.py'}, 'templates': {'.html', '.js'},
            'locale': {'.po'}, 'frontend': {'.css'}, 'licenses': {'.txt'},
            'static': {'.js', '.css', '.svg', '.png', '.ico'},
            'scripts': {'.py', '.cjs'}}


def repository_files():
    for name in sorted(ROOT_FILES):
        path = ROOT / name
        if path.is_file():
            yield path
    for directory, suffixes in SUFFIXES.items():
        for path in sorted((ROOT / directory).rglob('*')):
            if path.is_file() and path.suffix in suffixes and '__pycache__' not in path.parts:
                if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
                    raise ValueError('Source contains a link outside the project')
                yield path
