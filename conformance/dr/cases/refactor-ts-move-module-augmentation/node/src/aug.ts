import { X } from './a.js';

declare module './a.js' {
  interface Extra {
    y: number;
  }
}

export const c = X;
