import { AcmeModel } from './compat';

export function make(): object {
  const Model = 1;
  return [Model, new AcmeModel()];
}
