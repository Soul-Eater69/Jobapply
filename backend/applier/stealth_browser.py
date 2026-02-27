"""
Stealth browser setup using Playwright.

Anti-detection layers:
  1.  navigator.webdriver = undefined
  2.  Realistic plugin/mime-type list
  3.  navigator.languages / platform / hardwareConcurrency spoofing
  4.  Canvas fingerprint pixel-jitter noise
  5.  WebGL renderer spoofing (Intel Iris)
  6.  Chrome runtime injection (window.chrome)
  7.  Permissions API passthrough
  8.  Headless Chrome UA replacement
  9.  Realistic screen colorDepth / pixelDepth
  10. Connection info spoofing
  11. Poisson-distributed delays between all interactions
  12. Bezier-curve mouse movement (Python-tracked position, no JS state)
  13. Human typing: Gaussian speed + 2% typo+correction rate

Human simulation:
  - warm_up_session()     : browse site naturally before applying
  - read_page_like_human(): scroll + random hover, simulate reading time
  - detect_captcha()      : detect CAPTCHA so caller can halt + notify
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

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 800},
    {"width": 2560, "height": 1440},
    {"width": 1366, "height": 768},
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

STEALTH_SCRIPT = """
// ── 1. Remove webdriver flag ──────────────────────────────────────────────────
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// ── 2. Realistic plugin list ──────────────────────────────────────────────────
const _fakePlugins = [
  { name: 'Chrome PDF Plugin',  description: 'Portable Document Format', filename: 'internal-pdf-viewer',         length: 0 },
  { name: 'Chrome PDF Viewer',  description: '',                          filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', length: 0 },
  { name: 'Native Client',      description: '',                          filename: 'internal-nacl-plugin',        length: 0 },
];
Object.defineProperty(navigator, 'plugins', { get: () => _fakePlugins });

// ── 3. Language / platform / hardware spoofing ────────────────────────────────
Object.defineProperty(navigator, 'languages',           { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'platform',            { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory',        { get: () => 8 });
Object.defineProperty(navigator, 'maxTouchPoints',      { get: () => 0 });

// ── 4. Chrome runtime injection ───────────────────────────────────────────────
window.chrome = {
  app: {
    isInstalled: false,
    InstallState: { DISABLED:'disabled', INSTALLED:'installed', NOT_INSTALLED:'not_installed' },
    RunningState:  { CANNOT_RUN:'cannot_run', READY_TO_RUN:'ready_to_run', RUNNING:'running' }
  },
  csi: () => {},
  loadTimes: () => ({}),
  runtime: { onConnect: { addListener: () => {} }, onMessage: { addListener: () => {} } },
};

// ── 5. Permissions API passthrough ────────────────────────────────────────────
if (window.navigator.permissions) {
  const _orig = navigator.permissions.query.bind(navigator.permissions);
  navigator.permissions.query = (p) =>
    p.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : _orig(p);
}

// ── 6. Canvas fingerprint noise ───────────────────────────────────────────────
const _toDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type, ...args) {
  const ctx = this.getContext('2d');
  if (ctx && this.width > 0 && this.height > 0) {
    const img = ctx.getImageData(0, 0, this.width, this.height);
    for (let i = 0; i < img.data.length; i += 4) {
      if (Math.random() < 0.3) img.data[i]   = Math.min(255, img.data[i]   + 1);
      if (Math.random() < 0.3) img.data[i+1] = Math.min(255, img.data[i+1] + 1);
    }
    ctx.putImageData(img, 0, 0);
  }
  return _toDataURL.call(this, type, ...args);
};

// ── 7. WebGL renderer spoofing ────────────────────────────────────────────────
const _patchWebGL = (ctx) => {
  if (!ctx) return;
  const _gp = ctx.prototype.getParameter;
  ctx.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel Iris OpenGL Engine';
    return _gp.call(this, p);
  };
};
_patchWebGL(window.WebGLRenderingContext);
if (window.WebGL2RenderingContext) _patchWebGL(window.WebGL2RenderingContext);

// ── 8. Replace HeadlessChrome UA ─────────────────────────────────────────────
if (navigator.userAgent.includes('HeadlessChrome')) {
  Object.defineProperty(navigator, 'userAgent', {
    get: () => navigator.userAgent.replace('HeadlessChrome', 'Chrome'),
  });
}

// ── 9. Screen properties ──────────────────────────────────────────────────────
Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });

// ── 10. Connection spoofing ───────────────────────────────────────────────────
if (navigator.connection) {
  try {
    Object.defineProperty(navigator.connection, 'rtt',           { get: () => 100 });
    Object.defineProperty(navigator.connection, 'downlink',      { get: () => 10  });
    Object.defineProperty(navigator.connection, 'effectiveType', { get: () => '4g'});
    Object.defineProperty(navigator.connection, 'saveData',      { get: () => false });
  } catch (_) {}
}
"""

# Known CAPTCHA detection signatures
CAPTCHA_SELECTORS = [
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "iframe[src*='cloudflare']",
    ".g-recaptcha",
    ".h-captcha",
    "#captcha",
    "[class*='captcha']",
    "[id*='captcha']",
    "[class*='cf-challenge']",
]
CAPTCHA_TEXT = [
    "verify you are human",
    "prove you're not a robot",
    "security check",
    "unusual traffic",
    "access denied",
    "just a moment",     # Cloudflare
]

WARMUP_PATHS = {
    "linkedin":     ["https://www.linkedin.com/", "https://www.linkedin.com/jobs/"],
    "indeed":       ["https://www.indeed.com/"],
    "glassdoor":    ["https://www.glassdoor.com/"],
    "ziprecruiter": ["https://www.ziprecruiter.com/"],
    "dice":         ["https://www.dice.com/"],
}


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
        # Track mouse in Python — avoids relying on fragile JS state
        self._mouse_x: float = self.viewport["width"] / 2
        self._mouse_y: float = self.viewport["height"] / 2

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
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-renderer-backgrounding",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-ipc-flooding-protection",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-default-apps",
                "--disable-notifications",
                f"--window-size={self.viewport['width']},{self.viewport['height']}",
            ],
            "ignore_default_args": [
                "--enable-automation",
                "--enable-blink-features=IdleDetection",
            ],
        }
        if self.proxy:
            launch_kwargs["proxy"] = {"server": self.proxy}

        self._browser = await self._playwright.chromium.launch(**launch_kwargs)

        session_path = SESSIONS_DIR / self.session_name
        tz = random.choice([
            "America/New_York", "America/Chicago",
            "America/Los_Angeles", "America/Denver",
            "Europe/London", "Europe/Berlin",
        ])
        context_kwargs = dict(
            viewport=self.viewport,
            user_agent=self.user_agent,
            locale="en-US",
            timezone_id=tz,
            color_scheme="light",
            accept_downloads=True,
        )
        if (session_path / "state.json").exists():
            context_kwargs["storage_state"] = str(session_path / "state.json")

        self._context = await self._browser.new_context(**context_kwargs)
        await self._context.add_init_script(STEALTH_SCRIPT)
        return self

    async def new_page(self) -> Page:
        page = await self._context.new_page()
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
            sp = SESSIONS_DIR / self.session_name
            sp.mkdir(exist_ok=True)
            await self._context.storage_state(path=str(sp / "state.json"))

    async def close(self):
        await self.save_session()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


# ─── Timing ───────────────────────────────────────────────────────────────────

async def poisson_delay(mean_seconds: float = 2.0):
    """Poisson / exponential delay — more realistic than uniform random."""
    d = random.expovariate(1.0 / max(mean_seconds, 0.1))
    await asyncio.sleep(max(0.3, min(d, mean_seconds * 5)))


# ─── Mouse ────────────────────────────────────────────────────────────────────

async def bezier_mouse_move(
    page: Page,
    target_x: float,
    target_y: float,
    browser: Optional[StealthBrowser] = None,
):
    """Cubic bezier curve mouse movement. Position tracked in Python."""
    if browser:
        sx, sy = browser._mouse_x, browser._mouse_y
    else:
        sx, sy = random.uniform(200, 800), random.uniform(200, 600)

    dist = math.hypot(target_x - sx, target_y - sy)
    steps = max(8, min(int(dist / 25), 35))

    cp1x = sx + random.uniform(-100, 100)
    cp1y = sy + random.uniform(-100, 100)
    cp2x = target_x + random.uniform(-50, 50)
    cp2y = target_y + random.uniform(-50, 50)

    for i in range(steps + 1):
        t = i / steps
        bx = ((1-t)**3*sx + 3*(1-t)**2*t*cp1x + 3*(1-t)*t**2*cp2x + t**3*target_x)
        by = ((1-t)**3*sy + 3*(1-t)**2*t*cp1y + 3*(1-t)*t**2*cp2y + t**3*target_y)
        await page.mouse.move(bx, by)
        await asyncio.sleep(max(0.003, random.gauss(0.009, 0.003)))

    if browser:
        browser._mouse_x = target_x
        browser._mouse_y = target_y


async def human_click(
    page: Page,
    selector: str,
    browser: Optional[StealthBrowser] = None,
):
    """Move to selector → hover → click with natural timing."""
    el = await page.wait_for_selector(selector, timeout=10000)
    await human_click_element(page, el, browser)


async def human_click_element(
    page: Page,
    element,
    browser: Optional[StealthBrowser] = None,
):
    """Click a resolved element handle with bezier movement."""
    box = await element.bounding_box()
    if not box:
        await element.click()
        return
    x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
    y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
    await bezier_mouse_move(page, x, y, browser)
    await asyncio.sleep(random.uniform(0.06, 0.18))
    await page.mouse.down()
    await asyncio.sleep(random.uniform(0.04, 0.12))
    await page.mouse.up()


# ─── Typing ───────────────────────────────────────────────────────────────────

async def human_type_element(element, text: str, clear_first: bool = True):
    """
    Type into an element with Gaussian speed + 2% typo-then-correct rate.
    Uses element directly — no selector string needed.
    """
    await element.click()
    await asyncio.sleep(random.uniform(0.1, 0.35))

    if clear_first:
        await element.press("Control+a")
        await asyncio.sleep(random.uniform(0.05, 0.12))
        await element.press("Delete")
        await asyncio.sleep(random.uniform(0.05, 0.18))

    for char in text:
        if random.random() < 0.02 and char.isalpha():
            typo = random.choice("qwertyuiopasdfghjklzxcvbnm")
            await element.type(typo)
            await asyncio.sleep(random.uniform(0.07, 0.2))
            await element.press("Backspace")
            await asyncio.sleep(random.uniform(0.07, 0.18))

        delay_ms = max(30, min(int(random.gauss(72, 20)), 190))
        await element.type(char)
        await asyncio.sleep(delay_ms / 1000)

        if random.random() < 0.03:
            await asyncio.sleep(random.uniform(0.25, 1.0))


# ─── Scroll ───────────────────────────────────────────────────────────────────

async def random_scroll(page: Page):
    for _ in range(random.randint(2, 5)):
        await page.mouse.wheel(0, random.randint(150, 500))
        await asyncio.sleep(random.uniform(0.4, 1.6))


async def read_page_like_human(page: Page, browser: Optional[StealthBrowser] = None):
    """Scroll + hover on random elements to simulate reading."""
    vh = browser.viewport["height"] if browser else 800
    total_h = await page.evaluate("() => document.body.scrollHeight")
    target = min(total_h * 0.65, vh * 3)
    scrolled = 0

    while scrolled < target:
        chunk = random.randint(70, 240)
        await page.mouse.wheel(0, chunk)
        scrolled += chunk
        await asyncio.sleep(max(0.2, random.gauss(0.55, 0.18)))

        if random.random() < 0.18:
            try:
                els = await page.query_selector_all("a, p, li, h2, h3")
                if els:
                    el = random.choice(els[:25])
                    box = await el.bounding_box()
                    if box and box["y"] > 0:
                        await bezier_mouse_move(
                            page,
                            box["x"] + box["width"] * 0.5,
                            box["y"] + box["height"] * 0.5,
                            browser,
                        )
                        await asyncio.sleep(random.uniform(0.15, 0.6))
            except Exception:
                pass


# ─── CAPTCHA ──────────────────────────────────────────────────────────────────

async def detect_captcha(page: Page) -> bool:
    """Return True if a CAPTCHA or bot-check page is detected."""
    for sel in CAPTCHA_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                return True
        except Exception:
            pass

    try:
        content = (await page.content()).lower()
        if any(t in content for t in CAPTCHA_TEXT):
            return True
        title = (await page.title()).lower()
        if any(t in title for t in ["captcha", "blocked", "verify", "challenge"]):
            return True
    except Exception:
        pass

    return False


# ─── Warm-up ──────────────────────────────────────────────────────────────────

async def warm_up_session(
    page: Page,
    platform: str,
    browser: Optional[StealthBrowser] = None,
):
    """
    Browse the platform naturally for ~20s before the first apply.
    Builds realistic session history and avoids "apply immediately" detection.
    """
    paths = WARMUP_PATHS.get(platform, [])
    for path in paths:
        try:
            await page.goto(path, wait_until="domcontentloaded", timeout=20000)
            await poisson_delay(random.uniform(1.5, 3.0))
            await read_page_like_human(page, browser)
            await poisson_delay(random.uniform(0.8, 2.0))
        except Exception as e:
            logger.debug(f"Warmup step failed [{platform}] {path}: {e}")
    logger.info(f"Session warmed up for {platform}")
