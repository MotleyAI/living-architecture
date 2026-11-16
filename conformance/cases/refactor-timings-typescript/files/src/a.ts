export function foo(): number {
  return 1;
}

export class Base {
  run(): number {
    return foo();
  }
}
