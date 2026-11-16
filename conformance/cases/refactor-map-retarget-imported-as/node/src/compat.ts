import { Target as Local } from './home';

export const Alias = Local;

export function f(): object {
  return new Alias();
}
