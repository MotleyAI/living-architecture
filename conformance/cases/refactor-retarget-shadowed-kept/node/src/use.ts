import { AcmeModel } from './models';

export function make(): object {
  const Model = 1;
  return [Model, new AcmeModel()];
}

export function other(): object {
  return new AcmeModel();
}
