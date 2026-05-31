import { launchBrowser, openPortal } from './browser.js';

async function main() {
  await launchBrowser({ headless: false });
  const scopus = await openPortal('scopus');
  console.log('[paper-fetcher-mcp] Browser launched.');
  console.log('[paper-fetcher-mcp] Opened Scopus:', scopus.url);
  console.log('[paper-fetcher-mcp] Complete manual login in the opened browser window.');
  console.log('[paper-fetcher-mcp] Keep the browser open until login is done.');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
