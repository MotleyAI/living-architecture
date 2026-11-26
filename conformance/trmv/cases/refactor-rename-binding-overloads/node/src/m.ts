export function old(x: number): number;
export function old(x: string): string;
export function old(x: number | string): number | string {
  return x;
}

export const y = old(1);
