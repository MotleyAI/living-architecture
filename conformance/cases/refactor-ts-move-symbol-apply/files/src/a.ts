import { foo } from "./b";

export class Base {
  run(): number {
    return foo();
  }
}
