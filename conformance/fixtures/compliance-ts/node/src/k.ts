import { vi } from 'vitest';

interface Item {
  id: number;
}

export function f(a, { b }, ...rest) {
  return [a, b, rest];
}

export function ids(items: Item[]): number[] {
  return items.map((x) => x.id);
}

export function loose(value: any): any[] {
  return [value as any];
}

export const typed = (n: number): number => n;

export const spy = vi.fn();
