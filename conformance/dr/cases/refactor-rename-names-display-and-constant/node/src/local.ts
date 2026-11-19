import { Ds } from './m';

export function local(d: Ds): unknown {
  let key = 'columns';
  return Reflect.get(d, key);
}
