import { vi } from 'vitest';
import { vi as v } from 'vitest';
import { jest as j } from '@jest/globals';
import { get } from '../src/api';

export const a = vi.fn();
export const b = vi.fn<typeof get>();
export const c = vi.fn(() => 1);
export const d = v.fn();
export const e = j.fn();
export const g = jest.fn();

vi.mock('../src/api', () => ({ get: vi.fn<typeof get>() }));
vi.mock(import('../src/api'), () => ({ get: vi.fn<typeof get>() }));
vi.mock('../src/api');
vi.mock('../src/api', { spy: true });
vi.mock(import('../src/nope'), () => ({}));
vi.doMock('../src/api', () => ({}));
j.mock<typeof import('../src/api')>('../src/api', () => ({ get: j.fn<typeof get>() }));
j.mock('../src/api', () => ({}));
j.unstable_mockModule('../src/api', () => ({}));

interface Db {
  query(): number;
}
export const db = {} as unknown as Db;
export const db2 = {} as any as Db;
