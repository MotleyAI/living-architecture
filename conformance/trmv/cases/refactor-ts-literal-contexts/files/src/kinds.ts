export type Kind = 'edit_master' | 'drop';
export type Other = 'edit_model' | 'zzz';

export function take(k: Kind): Kind {
  return k;
}

export function isEdit(x: Kind): boolean {
  return x === 'edit_master';
}

export function check(x: Kind): boolean {
  const typed: Kind = 'edit_master';
  const list: Kind[] = ['edit_master'];
  const other: Other = 'edit_model';
  const s: string = 'edit_model';
  take('edit_master');
  switch (x) {
    case 'edit_master':
      return typed === x && list.length > 0 && other.length > 0 && s.length > 0;
    default:
      return false;
  }
}
