import path from 'node:path';

export const SCIENCE_ROOT = process.env.SCIENCE_ROOT || '/Users/avalont/Projects/knowledge/Science';
export const BROWSER_PROFILE_DIR = process.env.BROWSER_PROFILE_DIR || path.join(SCIENCE_ROOT, 'browser-profile');
export const PDF_DOWNLOAD_DIR = process.env.PDF_DOWNLOAD_DIR || path.join(SCIENCE_ROOT, 'pdfs');
export const HEADLESS = process.env.HEADLESS === 'true';

export const PORTALS = {
  scopus: 'https://www.scopus.com/pages/home',
  worldcat: 'https://utrechtuniversity.on.worldcat.org/',
  sciencedirect: 'https://www.sciencedirect.com/'
} as const;

export type PortalName = keyof typeof PORTALS;
