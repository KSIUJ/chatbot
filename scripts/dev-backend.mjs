// Backend do `pnpm dev`: migracje bazy (jak przy starcie w Dockerze), potem
// uvicorn z przeladowaniem na 127.0.0.1:8000 - tam, gdzie proxy vite
// (src/frontend/vite.config.ts) przekazuje /api. Python z .venv (pnpm setup:backend).
import { spawn, spawnSync } from 'node:child_process';
import { requireVenv, root, venvPython as python } from './venv.mjs';

requireVenv();

const migrate = spawnSync(python, ['-m', 'alembic', 'upgrade', 'head'], { cwd: root, stdio: 'inherit' });
if (migrate.status !== 0) process.exit(migrate.status ?? 1);

// --reload-dir src: zmiany w .venv, node_modules, data/ i dataset/ nie restartuja
// backendu. Uwaga: .env jest czytany tylko przy starcie procesu - po jego zmianie
// zrestartuj `pnpm dev` (albo zapisz dowolny plik .py).
const uvicorn = spawn(
  python,
  ['-m', 'uvicorn', 'src.backend.main:app', '--reload', '--reload-dir', 'src', '--host', '127.0.0.1', '--port', '8000'],
  { cwd: root, stdio: 'inherit' },
);
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => uvicorn.kill(signal));
}
uvicorn.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
