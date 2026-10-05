import type { Ledger } from '../core/ledger';
import { shout } from '../util/fmt';

export function handle(raw: unknown): number {
  return Number(raw);
}

export function describeLedger(label: string, ledger: Ledger): string {
  return `${shout(label)}: ${ledger.total()}`;
}
