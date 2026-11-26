export function f(name: string): string {
  const model = name.toUpperCase();
  return model;
}

export class Q {
  run(name: string): string {
    const model = name.toLowerCase();
    return model;
  }
}

export const k = (name: string): string => {
  const model = name.trim();
  return model;
};

export function h(model: string): string {
  return model;
}
