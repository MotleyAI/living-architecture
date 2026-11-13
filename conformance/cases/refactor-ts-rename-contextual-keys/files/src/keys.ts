export class Model {
  fields: number[] = [];

  static validate(d: Partial<Model>): Model {
    return Object.assign(new Model(), d);
  }
}

export const a = Model.validate({ fields: [] });
export const b: Model = { fields: [] };
export const c = { columns: [] };
