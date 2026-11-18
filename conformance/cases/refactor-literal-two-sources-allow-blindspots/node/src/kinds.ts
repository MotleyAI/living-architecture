export type Kind = 'edit_model' | 'drop';

export function take(k: Kind): void {
  console.log(k);
}
