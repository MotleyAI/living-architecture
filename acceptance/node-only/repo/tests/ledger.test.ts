import { describe, expect, it } from 'vitest';
import { Ledger } from '../src/core/ledger';

describe('ledger', () => {
  it('totals its entries', () => {
    const ledger = new Ledger();
    ledger.add(150);
    ledger.add(50);
    expect(ledger.total()).toBe('2.00 EUR');
  });
});
