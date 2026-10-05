import { describe, expect, it, vi } from 'vitest';
import { describeLedger, handle } from '../src/api/handler';
import type { Ledger } from '../src/core/ledger';

vi.mock('../src/core/money', () => ({ CURRENCY: 'USD' }));

describe('handler', () => {
  it('parses numbers', () => {
    expect(handle('42')).toBe(42);
  });

  it('describes a ledger', () => {
    const total = vi.fn();
    total.mockReturnValue('1.00 USD');
    const ledger = { total } as unknown as Ledger;
    expect(describeLedger('cash', ledger)).toBe('CASH: 1.00 USD');
  });
});
