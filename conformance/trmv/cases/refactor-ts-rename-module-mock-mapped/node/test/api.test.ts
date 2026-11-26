import { vi } from 'vitest';
import { get } from '@/api';

vi.mock('@/api');

export const shown = get();
