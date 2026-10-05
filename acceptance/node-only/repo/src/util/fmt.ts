import { CURRENCY } from '../core/money';

export function formatAmount(cents: number): string {
  return `${(cents / 100).toFixed(2)} ${CURRENCY}`;
}

export function shout(text: string): string {
  return text.toUpperCase();
}
