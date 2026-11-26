import { f } from './kinds';

let DEFAULT: 'edit_model' | 'drop' | 'none';
if (Math.random() < 0.5) {
  DEFAULT = 'drop';
} else {
  DEFAULT = 'edit_model';
}

f(DEFAULT);
