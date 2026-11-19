export type Kind = 'edit_model' | 'drop';

export function f(kind: Kind): void {
  console.log(kind);
}
