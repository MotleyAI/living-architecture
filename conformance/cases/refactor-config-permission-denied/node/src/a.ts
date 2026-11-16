export function foo(): number {
  return 1;
}

export const use = (): number => foo() + 1;
