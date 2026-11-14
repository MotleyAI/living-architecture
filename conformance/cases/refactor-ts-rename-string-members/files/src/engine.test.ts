import { vi } from 'vitest';
import { Engine } from './engine';

export function spies(engine: Engine): void {
  vi.spyOn(engine, 'persistModel');
  vi.spyOn(Engine.prototype, 'persistModel');
  jest.spyOn(engine, "persistModel");
  Reflect.get(engine, 'persistModel');
  Reflect.has(Engine.prototype, 'persistModel');
  Object.defineProperty(engine, 'persistModel', { value: () => undefined });
  Object.getOwnPropertyDescriptor(Engine.prototype, 'persistModel');
  Reflect.set(engine, 'persistModel', () => undefined);
  Reflect.deleteProperty(engine, 'persistModel');
  Reflect.defineProperty(engine, 'persistModel', { value: () => undefined });
  Reflect.getOwnPropertyDescriptor(Engine.prototype, 'persistModel');
  Reflect.get(engine, 'saveModelX');
}
