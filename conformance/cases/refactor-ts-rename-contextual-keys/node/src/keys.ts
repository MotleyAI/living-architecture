export class Model {
  columns: number[] = [];

  static validate(d: Partial<Model>): Model {
    return Object.assign(new Model(), d);
  }
}

export const a = Model.validate({ columns: [] });
export const b: Model = { columns: [] };
export const c = { columns: [] };
