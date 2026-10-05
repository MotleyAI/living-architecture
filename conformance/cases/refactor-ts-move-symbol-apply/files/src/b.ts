import { Base } from './a';

export class Child extends Base {
  override run(): number {
    return foo() + 1;
  }
}

export function foo(): number {
    return 1;
}
