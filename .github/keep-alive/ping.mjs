// Abre la app de Streamlit con un navegador real para registrar una sesión
// (websocket) activa y reiniciar el temporizador de inactividad. Si la app
// está dormida, pulsa el botón para despertarla.
import { chromium } from 'playwright';

const url = process.env.APP_URL;
if (!url) {
  console.error('Falta la variable APP_URL');
  process.exit(1);
}

const browser = await chromium.launch();
const page = await browser.newPage();

console.log(`Abriendo ${url}`);
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });

// Si la app está dormida, Streamlit muestra un botón para reactivarla.
try {
  const wake = page.getByText(/get this app back up/i);
  if (await wake.isVisible({ timeout: 5000 })) {
    console.log('App dormida detectada: pulsando botón para despertarla...');
    await wake.click();
  }
} catch {
  // No estaba dormida; seguimos.
}

// Esperar a que la app de Streamlit conecte (sesión activa real).
try {
  await page.waitForSelector('[data-testid="stApp"]', { timeout: 90000 });
  console.log('App de Streamlit cargada y conectada.');
} catch {
  console.log('No se detectó stApp a tiempo; la reactivación pudo iniciarse igual.');
}

// Mantener la sesión abierta para que cuente como una visita real.
await page.waitForTimeout(20000);
console.log('Sesión mantenida. Keep-alive completo.');

await browser.close();
