import { handle } from '../api/handlers';
import { run } from '../core/service';

export const save = (x?: unknown) => [x, handle, run];
