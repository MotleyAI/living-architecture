import { b } from './b';

export async function load() {
  const m = await import('./m');
  return m.default;
}

export const lazy = () => import('./lazy');
let t: import('./types').T;
declare module 'ext' {
  import { Base } from 'base';
  export const v: Base;
}
namespace Shapes {
  export const k = 1;
  import { Base } from 'base';
  import Alias = Geometry.Base;
}
export { b, t };
