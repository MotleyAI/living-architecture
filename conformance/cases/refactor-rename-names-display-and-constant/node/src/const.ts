import { Ds } from './m';

const NAME = 'columns';

export function read(d: Ds): unknown {
  return d[NAME];
}
