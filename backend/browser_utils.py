import os
import random
from typing import Optional
from playwright.async_api import async_playwright, BrowserContext
from playwright_stealth import Stealth

USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Chrome Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Safari Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    # Edge Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
]

async def create_stealth_context(pw_instance, headless: bool = True) -> BrowserContext:
    """
    Creates a new Playwright browser context configured with stealth techniques,
    randomized user-agents, and optional proxy routing.
    """
    proxy_url = os.getenv("PROXY_URL")
    proxy_config = {"server": proxy_url} if proxy_url else None
    
    # Launch browser
    browser = await pw_instance.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--window-position=0,0",
            "--ignore-certificate-errors",
            "--ignore-certificate-errors-spki-list",
        ],
        proxy=proxy_config
    )
    
    # Randomize viewport and user agent
    ua = random.choice(USER_AGENTS)
    viewport = {"width": random.choice([1366, 1440, 1536, 1920]), "height": random.choice([768, 900, 864, 1080])}
    
    # Create context
    context = await browser.new_context(
        user_agent=ua,
        viewport=viewport,
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        color_scheme="dark",
        device_scale_factor=random.choice([1, 2])
    )
    
    # Optional: Attach stealth to every new page created in this context
    # We will explicitly apply stealth_async(page) to each page after creating it
    # to ensure it's fully applied.
    
    return browser, context

async def create_stealth_page(context: BrowserContext):
    """Creates a new page in the context and applies stealth."""
    page = await context.new_page()
    await Stealth().apply_stealth_async(page)
    return page
