export function f(name: string): string {
  const model = name.toUpperCase();
  return model;
}

export function g(name: string): string {
  const model = name.toLowerCase();
  return model;
}

export function k(name: string): string {
  const dataset = name;
  const model = name.trim();
  return model + dataset;
}
