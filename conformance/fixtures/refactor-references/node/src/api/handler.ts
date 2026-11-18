import { X } from '../sql/client.js';
import { connect } from '../sql/engine.js';

export function handle(): number {
  return X + connect();
}
