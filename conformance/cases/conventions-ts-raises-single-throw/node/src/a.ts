export function f(): void {
  expect(() => parse(load())).toThrow();
}
