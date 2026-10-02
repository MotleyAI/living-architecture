// The package root: its version, from package.json next to src/ or dist/.
import { readFileSync } from 'node:fs';

export const VERSION: string = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version;
