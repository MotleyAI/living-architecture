// The TypeScript compiler, loaded on first use so commands that never parse TypeScript start without it.
import { createRequire } from 'node:module';
import type * as TS from 'typescript';

let compiler: typeof TS | undefined;

export function ts(): typeof TS {
  compiler ??= createRequire(import.meta.url)('typescript') as typeof TS;
  return compiler;
}
