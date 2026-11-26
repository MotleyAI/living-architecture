import { Engine } from './engine';

/** Calls {@link Engine.saveModel}; saveModel is async. */
export function f(e: Engine): void {
  // see Engine#saveModel
  console.log('saveModel');
  e.saveModel('x');
}
