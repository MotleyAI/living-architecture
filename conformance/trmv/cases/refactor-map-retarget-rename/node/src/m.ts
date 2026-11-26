export function target(): number {
  return 1;
}

export const old_alias = target;

export function f(): number {
  return old_alias();
}
