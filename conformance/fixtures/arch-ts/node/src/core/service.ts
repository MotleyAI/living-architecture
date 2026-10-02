import { save } from '../store/db';
import { u } from '../util';

export const run = () => save(u);
