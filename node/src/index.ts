// The package root: its version, from package.json next to src/ or dist/, and its native language.
import { readFileSync } from 'node:fs';

export const VERSION: string = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version;
export const NATIVE_LANGUAGE = 'typescript';
