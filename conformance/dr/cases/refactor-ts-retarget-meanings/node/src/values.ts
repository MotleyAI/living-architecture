import { Flight } from './compat';

export const v = new Flight();
export const w: Flight = v;
export type V = typeof Flight;
export class Sub extends Flight {}
