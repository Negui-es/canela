const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const root = path.resolve(__dirname, '..');
fs.mkdirSync(path.join(root, 'static/vendor'), {recursive: true});
fs.copyFileSync(path.join(root,'node_modules/htmx.org/dist/htmx.min.js'),path.join(root,'static/vendor/htmx.min.js'));
fs.copyFileSync(path.join(root,'node_modules/alpinejs/dist/cdn.min.js'),path.join(root,'static/vendor/alpine.min.js'));
const cli = path.join(root, 'node_modules/@tailwindcss/cli/dist/index.mjs');
cp.execFileSync(process.execPath, [cli, '-i', 'frontend/tailwind.css', '-o', 'static/css/utilities.css', '--minify'], {cwd:root,stdio:'inherit'});
