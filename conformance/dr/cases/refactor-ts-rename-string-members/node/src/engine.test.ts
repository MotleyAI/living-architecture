import { vi } from 'vitest';
import { Engine } from './engine';

export function spies(engine: Engine): void {
  vi.spyOn(engine, 'saveModel');
  vi.spyOn(Engine.prototype, 'saveModel');
  jest.spyOn(engine, "saveModel");
  Reflect.get(engine, 'saveModel');
  Reflect.has(Engine.prototype, 'saveModel');
  Object.defineProperty(engine, 'saveModel', { value: () => undefined });
  Object.getOwnPropertyDescriptor(Engine.prototype, 'saveModel');
  Reflect.set(engine, 'saveModel', () => undefined);
  Reflect.deleteProperty(engine, 'saveModel');
  Reflect.defineProperty(engine, 'saveModel', { value: () => undefined });
  Reflect.getOwnPropertyDescriptor(Engine.prototype, 'saveModel');
  Reflect.get(engine, 'saveModelX');
}
