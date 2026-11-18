export class Base extends Error {
  constructor(msg: string) {
    super(msg)
  }
}

export class A extends Base {
  readonly label: string

  constructor(msg: string, field: string) {
    super(msg)
    this.label = field
  }
}

export class B extends Base {
  readonly label: string

  constructor(msg: string, field: string) {
    super(`field of ${field}`)
    this.label = msg
  }
}

export class C extends A {
  constructor(msg: string, field: string) {
    super(msg, field)
  }
}
