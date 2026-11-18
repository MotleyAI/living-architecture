import { A, B, C } from './errors'

export function make(): Error[] {
  return [new A('x', 'a'), new B('y', 'b'), new C('z', 'c')]
}
