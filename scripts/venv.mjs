// Wspolne dla skryptow pnpm: katalog repo i Python z .venv (Windows: Scripts\python.exe,
// Linux/macOS: bin/python) oraz wymagana wersja z .python-version.
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const root = join(dirname(fileURLToPath(import.meta.url)), '..');

export const venvDir = join(root, '.venv');

export const venvPython = process.platform === 'win32'
  ? join(venvDir, 'Scripts', 'python.exe')
  : join(venvDir, 'bin', 'python');

/** Wersja Pythona projektu, np. "3.14". */
export const pythonVersion = readFileSync(join(root, '.python-version'), 'utf8').trim();

/** Konczy proces z podpowiedzia, gdy .venv jeszcze nie istnieje. */
export function requireVenv() {
  if (!existsSync(venvPython)) {
    console.error(`Brak .venv z Pythonem ${pythonVersion} - najpierw: pnpm setup:backend`);
    process.exit(1);
  }
}
