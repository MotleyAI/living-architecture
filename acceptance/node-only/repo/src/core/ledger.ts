import { formatAmount } from '../util/fmt';

export class Ledger {
  private readonly entries: number[] = [];

  add(cents: number): void {
    this.entries.push(cents);
  }

  total(): string {
    return formatAmount(this.entries.reduce((sum, cents) => sum + cents, 0));
  }
}
