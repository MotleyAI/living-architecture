import { run } from '../core/service';

export type Handler = () => unknown;
export const handle: Handler = () => run();
