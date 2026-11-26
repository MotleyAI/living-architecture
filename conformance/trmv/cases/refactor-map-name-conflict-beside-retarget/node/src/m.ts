export function target(): number {
  return 1;
}

export const old_alias = target;
export const spare = 2;

export function f(): number {
  return old_alias();
}

export function g(): number {
  const taken = 3;
  return spare + taken;
}
