import type { Ledger } from '../core/ledger';
import { shout } from '../util/fmt';

export function handle(raw: any): number {
  return Number.parseInt(String(raw), 10);
}

export function describeLedger(label, ledger: Ledger): string {
  return `${shout(label)}: ${ledger.total()}`;
}
