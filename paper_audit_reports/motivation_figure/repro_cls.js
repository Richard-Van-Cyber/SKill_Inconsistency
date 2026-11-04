// Minimal reproduction of finding fix-visual-stability|F-003.
// Question: does Chrome's CDP `Performance.getMetrics` ever return a metric
// named 'CumulativeLayoutShift' (the field the skill reads)?
const { chromium } = require('playwright');

const HTML = `<!doctype html><html><body style="margin:0">
  <div id="banner" style="height:0px;background:#333"></div>
  <p style="font:16px sans-serif">content</p>
  <img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='300'%3E%3C/svg%3E">
</body></html>`;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(HTML, { waitUntil: 'load' });

  // collect CLS the correct way (PerformanceObserver on layout-shift entries)
  await page.evaluate(() => {
    window.__cls = 0;
    new PerformanceObserver((l) => {
      for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value;
    }).observe({ type: 'layout-shift', buffered: true });
  });

  // force a large layout shift: banner grows after first paint
  await page.evaluate(() => new Promise((r) =>
    setTimeout(() => { document.getElementById('banner').style.height = '160px'; r(); }, 60)));
  await page.waitForTimeout(400);

  const truth = await page.evaluate(() => window.__cls);

  // ---- exactly what the skill does ----
  const session = await page.context().newCDPSession(page);
  const perf = await session.send('Performance.getMetrics');
  const metrics = {};
  for (const m of perf.metrics) metrics[m.name] = m.value;
  const cls = metrics['CumulativeLayoutShift'] || 0;          // skill line 44
  const rating = cls < 0.1 ? 'good' : cls < 0.25 ? 'needs-improvement' : 'poor';

  console.log('CDP metric names returned (%d):', perf.metrics.length);
  console.log('   ', perf.metrics.map(m => m.name).join(', '));
  console.log();
  console.log("has 'CumulativeLayoutShift'? ", 'CumulativeLayoutShift' in metrics);
  console.log('truthful CLS (PerformanceObserver):', truth.toFixed(4));
  console.log('skill reports  cls =', cls, ' rating =', JSON.stringify(rating));
  await browser.close();
})();
