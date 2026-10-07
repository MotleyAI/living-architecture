import { vi } from 'vitest';

vi.mock(import('virtual:config'), () => ({ flag: true }));
vi.mock(import('virtual:missing'), () => ({ flag: true }));
vi.mock(import('./theme.css'), () => ({ default: {} }));
