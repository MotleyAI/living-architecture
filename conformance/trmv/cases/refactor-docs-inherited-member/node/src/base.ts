export class Base {
  field = '';
}

/** Reads `field` of the base. */
export class Sub extends Base {}

export class Other {
  field = '';
}

/** Reads `field` of the other. */
export class Wrapper extends Other {}
