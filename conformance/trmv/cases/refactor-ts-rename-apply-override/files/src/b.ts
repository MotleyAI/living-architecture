import { Base, foo } from './a';

export class Child extends Base {
  override execute(): number {
    return foo() + 1;
  }
}
