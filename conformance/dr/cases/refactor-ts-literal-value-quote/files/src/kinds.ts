export type Kind = 'edit_model' | 'drop';
export type Other = 'edit_model' | 'zzz';

export function take(k: Kind): Kind {
  return k;
}

export function isEdit(x: Kind): boolean {
  return x === 'edit_model';
}

export function check(x: Kind): boolean {
  const typed: Kind = 'edit_model';
  const list: Kind[] = ['edit_model'];
  const other: Other = 'edit_model';
  const s: string = 'edit_model';
  take('edit_model');
  switch (x) {
    case 'edit_model':
      return typed === x && list.length > 0 && other.length > 0 && s.length > 0;
    default:
      return false;
  }
}
