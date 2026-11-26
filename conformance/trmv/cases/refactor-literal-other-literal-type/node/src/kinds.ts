export type Kind = 'edit_model' | 'drop';
export type Other = 'edit_model' | 'zzz';

export function f(kind: Kind): void {
  console.log(kind);
}

export function g(o: Other): void {
  console.log(o);
}
