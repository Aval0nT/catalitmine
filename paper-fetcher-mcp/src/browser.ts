import { chromium, type BrowserContext, type Page } from 'playwright';
import { BROWSER_PROFILE_DIR, HEADLESS, PDF_DOWNLOAD_DIR, PORTALS, type PortalName } from './config.js';

let context: BrowserContext | null = null;
let page: Page | null = null;

export async function launchBrowser(options?: { headless?: boolean }) {
  if (context) {
    return {
      context,
      page: page ?? (await context.newPage())
    };
  }

  context = await chromium.launchPersistentContext(BROWSER_PROFILE_DIR, {
    headless: options?.headless ?? HEADLESS,
    acceptDownloads: true,
    downloadsPath: PDF_DOWNLOAD_DIR
  });

  const pages = context.pages();
  page = pages[0] ?? (await context.newPage());

  return { context, page };
}

export async function getPage() {
  if (!context || !page) {
    return launchBrowser();
  }
  return { context, page };
}

export async function openPortal(portal: PortalName) {
  const { page } = await getPage();
  await page.goto(PORTALS[portal], { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('domcontentloaded');
  return {
    url: page.url(),
    title: await page.title()
  };
}

export async function closeBrowser() {
  if (context) {
    await context.close();
    context = null;
    page = null;
  }
}
