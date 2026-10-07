import { Base, foo } from './a';

export class Child extends Base {
  override run(): number {
    return foo() + 1;
  }
}
