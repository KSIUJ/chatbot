// Python z .venv z przekazanymi argumentami, niezaleznie od systemu, np.
// `node scripts/venv-python.mjs -m pytest -q` (pnpm test:backend).
import { spawnSync } from 'node:child_process';
import { requireVenv, root, venvPython } from './venv.mjs';

requireVenv();
const result = spawnSync(venvPython, process.argv.slice(2), { cwd: root, stdio: 'inherit' });
if (result.error) {
  console.error(`Nie udalo sie uruchomic ${venvPython}: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
