import { X } from '../src/sql/client.js';
import type { Client } from '../src/sql/client';
import legacy = require('../src/sql/client');

export { Client as Kept } from '../src/sql/client.js';
export * from '../src/sql/client.js';

export type Lazy = typeof import('../src/sql/client.js');
export const lazy = (): Promise<unknown> => import('../src/sql/client.js');

declare module '../src/sql/client.js' {
  interface Client {
    extra: number;
  }
}

export const both: number = X + legacy.X;
export type Shown = Client;
