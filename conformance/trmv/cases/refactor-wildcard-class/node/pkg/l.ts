export class Query {
  run(name: string): string {
    const model = name.toUpperCase();
    const inner = (): string => {
      const model = name.toLowerCase();
      return model;
    };
    return model + inner();
  }

  plan(name: string): string {
    const model = name.trim();
    return model;
  }
}

export function load(name: string): string {
  const model = name.trimEnd();
  return model;
}
