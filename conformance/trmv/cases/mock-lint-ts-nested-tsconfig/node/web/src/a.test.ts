import { vi } from 'vitest';

vi.mock(import('virtual:config'), () => ({ flag: true }));
