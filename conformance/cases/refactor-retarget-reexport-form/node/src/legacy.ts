import { Model as OldModel } from './core';

export { OldModel };

export function make(): object {
  return new OldModel();
}
