"""
Stealth browser setup using Playwright.
Implements advanced anti-detection techniques:
  - navigator.webdriver = undefined
  - Realistic screen/viewport dimensions
  - Plugin and mime-type spoofing
  - Canvas fingerprint noise
  - WebGL renderer spoofing
  - Chrome runtime injection
  - Realistic timing (Poisson-distributed delays)
  - Human-like mouse movements with bezier curves
  - Human-like typing with variable speed + mistakes
  - Cookie jar persistence
"""

import asyncio
import math
import random
import logging
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path(__file__).parent.parent.parent / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

# Realistic viewport sizes (common resolutions)
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 800},
    {"width": 2560, "height": 1440},
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

STEALTH_SCRIPT = """
// ── Stealth Patches ──────────────────────────────────────────────────────────

// 1. Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 2. Realistic plugin list
const makePlugin = (name, desc, filename, mimeTypes) => {
  const plugin = { name, description: desc, filename, length: mimeTypes.length };
  mimeTypes.forEach((mt, i) => { plugin[i] = mt; });
  return plugin;
};
const fakePlugins = [
  makePlugin('Chrome PDF Plugin', 'Portable Document Format', 'internal-pdf-viewer', []),
  makePlugin('Chrome PDF Viewer', '', 'mhjfbmdgcfjbbpaeojofohoefgiehjai', []),
  makePlugin('Native Client', '', 'internal-nacl-plugin', []),
];
Object.defineProperty(navigator, 'plugins', { get: () => fakePlugins });

// 3. Languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// 4. Platform
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

// 5. Hardware concurrency (realistic)
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

// 6. Device memory
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

// 7. Chrome runtime (fool checks for window.chrome)
window.chrome = {
  app: { isInstalled: false, InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }, RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' } },
  csi: () => {},
  loadTimes: () => {},
  runtime: {},
};

// 8. Permissions API — make it behave like a real browser
const originalQuery = window.navigator.permissions?.query?.bind(navigator.permissions);
if (originalQuery) {
  navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : originalQuery(parameters);
}

// 9. Canvas fingerprint noise — subtle pixel jitter
const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function (type, ...args) {
  const ctx = this.getContext('2d');
  if (ctx) {
    const imgData = ctx.getImageData(0, 0, this.width || 1, this.height || 1);
    for (let i = 0; i < imgData.data.length; i += 4) {
      imgData.data[i]     = Math.min(255, imgData.data[i]     + Math.floor(Math.random() * 2));
      imgData.data[i + 1] = Math.min(255, imgData.data[i + 1] + Math.floor(Math.random() * 2));
      imgData.data[i + 2] = Math.min(255, imgData.data[i + 2] + Math.floor(Math.random() * 2));
    }
    ctx.putImageData(imgData, 0, 0);
  }
  return origToDataURL.call(this, type, ...args);
};

// 10. WebGL renderer spoofing
const getParam = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function (parameter) {
  if (parameter === 37445) return 'Intel Inc.';
  if (parameter === 37446) return 'Intel Iris OpenGL Engine';
  return getParam.call(this, parameter);
};

// 11. Hide automation indicators in User-Agent
if (navigator.userAgent.includes('HeadlessChrome')) {
  Object.defineProperty(navigator, 'userAgent', {
    get: () => navigator.userAgent.replace('HeadlessChrome', 'Chrome'),
  });
}

// 12. Realistic screen properties
Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
"""


class StealthBrowser:
    def __init__(self, session_name: str = "default", headless: bool = True, proxy: str = None):
        self.session_name = session_name
        self.headless = headless
        self.proxy = proxy
        self.viewport = random.choice(VIEWPORTS)
        self.user_agent = random.choice(USER_AGENTS)
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def start(self):
        self._playwright = await async_playwright().start()
        launch_kwargs = {
            "headless": self.headless,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-position=0,0",
                "--ignore-certificate-errors",
                "--ignore-certificate-errors-spki-list",
                f"--window-size={self.viewport['width']},{self.viewport['height']}",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions-except=",
                "--disable-plugins-discovery",
                "--disable-default-apps",
                "--disable-notifications",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
            ],
            "ignore_default_args": ["--enable-automation", "--enable-blink-features=IdleDetection"],
        }

        if self.proxy:
            launch_kwargs["proxy"] = {"server": self.proxy}

        self._browser = await self._playwright.chromium.launch(**launch_kwargs)

        # Session persistence
        session_path = SESSIONS_DIR / f"{self.session_name}"
        context_kwargs = {
            "viewport": self.viewport,
            "user_agent": self.user_agent,
            "locale": "en-US",
            "timezone_id": random.choice(["America/New_York", "America/Chicago", "America/Los_Angeles", "America/Denver"]),
            "geolocation": {"longitude": -73.935242, "latitude": 40.730610},  # NY default
            "permissions": ["geolocation"],
            "color_scheme": "light",
            "accept_downloads": True,
        }

        if session_path.exists():
            self._context = await self._browser.new_context(
                storage_state=str(session_path / "state.json"),
                **context_kwargs,
            )
        else:
            self._context = await self._browser.new_context(**context_kwargs)

        # Inject stealth scripts into every new page
        await self._context.add_init_script(STEALTH_SCRIPT)
        return self

    async def new_page(self) -> Page:
        page = await self._context.new_page()

        # Random extra headers
        await page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        })

        return page

    async def save_session(self):
        if self._context:
            session_path = SESSIONS_DIR / self.session_name
            session_path.mkdir(exist_ok=True)
            await self._context.storage_state(path=str(session_path / "state.json"))

    async def close(self):
        await self.save_session()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


# ─── Human-like Interaction Helpers ─────────────────────────────────────────

async def poisson_delay(mean_seconds: float = 2.0):
    """Poisson-distributed delay — more realistic than uniform."""
    delay = random.expovariate(1.0 / mean_seconds)
    delay = max(0.5, min(delay, mean_seconds * 4))
    await asyncio.sleep(delay)


async def human_type(page: Page, selector: str, text: str, clear_first: bool = True):
    """Type text with human-like variable speed and occasional pauses."""
    await page.click(selector)
    await asyncio.sleep(random.uniform(0.2, 0.5))

    if clear_first:
        await page.keyboard.press("Control+a")
        await asyncio.sleep(0.1)
        await page.keyboard.press("Delete")
        await asyncio.sleep(random.uniform(0.1, 0.3))

    for i, char in enumerate(text):
        # Occasionally make typo and correct it (2% chance)
        if random.random() < 0.02 and char.isalpha():
            typo = random.choice("qwertyuiopasdfghjklzxcvbnm")
            await page.keyboard.type(typo, delay=0)
            await asyncio.sleep(random.uniform(0.08, 0.2))
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.1, 0.25))

        # Variable typing speed
        base_delay = random.gauss(80, 25)  # ms
        delay = max(30, min(base_delay, 200))

        await page.keyboard.type(char, delay=0)
        await asyncio.sleep(delay / 1000)

        # Occasional pause (thinking)
        if random.random() < 0.03:
            await asyncio.sleep(random.uniform(0.3, 1.2))


async def bezier_mouse_move(page: Page, x: int, y: int, steps: int = 8):
    """Move mouse along a bezier curve for natural movement."""
    current = await page.evaluate("() => ({ x: window.mouseX || 0, y: window.mouseY || 0 })")
    cx, cy = current.get("x", 0), current.get("y", 0)

    # Control points for bezier curve
    cp1x = cx + random.randint(-50, 50)
    cp1y = cy + random.randint(-50, 50)
    cp2x = x + random.randint(-30, 30)
    cp2y = y + random.randint(-30, 30)

    for i in range(steps + 1):
        t = i / steps
        bx = (1 - t) ** 3 * cx + 3 * (1 - t) ** 2 * t * cp1x + 3 * (1 - t) * t ** 2 * cp2x + t ** 3 * x
        by = (1 - t) ** 3 * cy + 3 * (1 - t) ** 2 * t * cp1y + 3 * (1 - t) * t ** 2 * cp2y + t ** 3 * y
        await page.mouse.move(bx, by)
        await asyncio.sleep(random.uniform(0.005, 0.015))


async def human_click(page: Page, selector: str):
    """Click with realistic mouse movement, random offset, natural timing."""
    element = await page.wait_for_selector(selector, timeout=10000)
    box = await element.bounding_box()
    if not box:
        await element.click()
        return

    # Click slightly off-center (humans don't click exactly center)
    x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
    y = box["y"] + box["height"] * random.uniform(0.3, 0.7)

    await bezier_mouse_move(page, int(x), int(y))
    await asyncio.sleep(random.uniform(0.05, 0.15))
    await page.mouse.down()
    await asyncio.sleep(random.uniform(0.05, 0.12))
    await page.mouse.up()


async def random_scroll(page: Page):
    """Simulate realistic reading scroll."""
    for _ in range(random.randint(2, 5)):
        scroll_amount = random.randint(200, 600)
        await page.mouse.wheel(0, scroll_amount)
        await asyncio.sleep(random.uniform(0.5, 1.5))
