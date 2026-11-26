import { foo } from '../../core/src/foo';
import { foo as aliased } from '@core/foo';

export const both = foo() + aliased();
