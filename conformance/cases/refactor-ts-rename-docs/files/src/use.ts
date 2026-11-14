import { Engine } from './engine';

/** Calls {@link Engine.persistModel}; saveModel is async. */
export function f(e: Engine): void {
  // see Engine#persistModel
  console.log('saveModel');
  e.persistModel('x');
}
