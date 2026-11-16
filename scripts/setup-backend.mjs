// `pnpm setup:backend`: .venv z Pythonem z .python-version, zaleznosci (grupa dev z pyproject.toml)
// i migracje bazy. Dziala na Windows (launcher `py`) i Linux/macOS (`python3.X`).
// Ponowne uruchomienie tylko doinstalowuje zaleznosci i migruje baze.
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { pythonVersion, root, venvDir, venvPython } from './venv.mjs';

/** Uruchamia polecenie w katalogu repo; konczy proces przy bledzie. */
function run(command, args) {
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit' });
  if (result.error) {
    console.error(`Nie udalo sie uruchomic ${command}: ${result.error.message}`);
    process.exit(1);
  }
  if (result.status !== 0) process.exit(result.status ?? 1);
}

/** Wersja Pythona (np. "3.14") podanego interpretera albo null, gdy go brak. */
function versionOf(command, args = []) {
  const result = spawnSync(
    command,
    [...args, '-c', 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")'],
    { cwd: root, encoding: 'utf8' },
  );
  return result.status === 0 ? result.stdout.trim() : null;
}

if (existsSync(venvPython)) {
  const found = versionOf(venvPython);
  if (found !== pythonVersion) {
    console.error(
      `.venv ma Pythona ${found ?? '(nie dziala)'}, projekt wymaga ${pythonVersion}. ` +
      'Usun katalog .venv i uruchom ponownie: pnpm setup:backend',
    );
    process.exit(1);
  }
} else {
  const [command, args] = process.platform === 'win32'
    ? ['py', [`-${pythonVersion}`]]
    : [`python${pythonVersion}`, []];
  if (versionOf(command, args) !== pythonVersion) {
    console.error(
      `Nie znaleziono Pythona ${pythonVersion} (${[command, ...args].join(' ')}). ` +
      'Zainstaluj go (python.org, pyenv albo uv python install) i uruchom ponownie.',
    );
    process.exit(1);
  }
  console.log(`Tworze .venv (Python ${pythonVersion})`);
  run(command, [...args, '-m', 'venv', venvDir]);
}

run(venvPython, ['-m', 'pip', 'install', '--group', 'dev']);
run(venvPython, ['-m', 'alembic', 'upgrade', 'head']);
