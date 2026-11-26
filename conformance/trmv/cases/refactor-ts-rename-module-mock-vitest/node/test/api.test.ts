import { vi } from 'vitest';
import { get } from '../src/api.js';

const factory = (): { get: () => number } => ({ get: () => 2 });

vi.mock('../src/api');
vi.doMock('../src/api.js', factory);
vi.unmock('../src/api');
vi.doUnmock('../src/api.js');
vi.mock(import('../src/api'), factory);

export const real = await vi.importActual('../src/api');
export const mocked = await vi.importMock('../src/api.js');
export const shown = get();
