import { legacy, type modern } from './api';

export const r: ReturnType<typeof modern> = legacy();
