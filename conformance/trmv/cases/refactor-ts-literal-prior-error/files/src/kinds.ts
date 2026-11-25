export type Kind = 'edit_master' | 'drop';

export function take(k: Kind): void {
  console.log(k);
}
