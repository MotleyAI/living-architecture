import { describe, expect, it, vi } from 'vitest';
import { describeLedger, handle } from '../src/api/handler';
import { Ledger } from '../src/core/ledger';

vi.mock(import('../src/core/money'), () => ({ CURRENCY: 'USD' }));

describe('handler', () => {
  it('parses numbers', () => {
    expect(handle('42')).toBe(42);
  });

  it('describes a ledger', () => {
    const ledger = new Ledger();
    const total = vi.spyOn(ledger, 'total');
    ledger.add(100);
    expect(describeLedger('cash', ledger)).toBe('CASH: 1.00 USD');
    expect(total).toHaveBeenCalledTimes(1);
  });

  it('records a typed double', () => {
    const report = vi.fn<(line: string) => void>();
    report(describeLedger('none', new Ledger()));
    expect(report).toHaveBeenCalledWith('NONE: 0.00 USD');
  });
});
