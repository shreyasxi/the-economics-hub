"""Keep the Streamlit app alive by visiting it with a headless browser.

Streamlit Community Cloud hibernates apps after 12 hours of inactivity.
This script visits the app, clicks the wake-up prompt if present, and waits
for the page to fully render — ensuring the 12-hour inactivity clock resets.
"""

# This file is named selenium.py, which would shadow the selenium library on
# sys.path[0] (the script's own directory). Remove it before any lib imports.
import sys
from pathlib import Path

_self_dir = str(Path(__file__).parent.resolve())
sys.path = [p for p in sys.path if p != _self_dir]

import logging
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

APP_URL = "https://weekly-macro-dashboard.streamlit.app/"
PAGE_LOAD_TIMEOUT = 90   # seconds to wait for initial page response
WAKE_BTN_TIMEOUT = 30    # seconds to check for the hibernation prompt
RENDER_TIMEOUT = 60      # seconds to wait for Streamlit content after wake
LINGER_SECONDS = 15      # seconds to stay on page so the server registers traffic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def build_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    # Mimic a real browser to avoid bot-detection on Streamlit's CDN
    options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver


def wake_app(driver: webdriver.Chrome) -> bool:
    log.info("Navigating to %s", APP_URL)
    driver.get(APP_URL)

    # --- Step 1: look for the Streamlit hibernation wake-up button ---
    try:
        wake_btn = WebDriverWait(driver, WAKE_BTN_TIMEOUT).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//*[contains(text(), 'Yes, get this app back up')]")
            )
        )
        log.info("Hibernation prompt detected — clicking wake-up button.")
        wake_btn.click()
    except Exception:
        log.info("No hibernation prompt found; app is likely already running.")

    # --- Step 2: wait for Streamlit's root element to appear ---
    try:
        WebDriverWait(driver, RENDER_TIMEOUT).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[data-testid='stApp'], .stApp, #root")
            )
        )
        log.info("Streamlit root element found — app is rendering.")
    except Exception:
        log.warning(
            "Streamlit root element not found within %d s. "
            "App may still be loading or URL may have changed.",
            RENDER_TIMEOUT,
        )

    title = driver.title
    log.info("Page title: '%s'", title)

    log.info("Lingering on page for %d seconds to register activity.", LINGER_SECONDS)
    time.sleep(LINGER_SECONDS)
    return True


def main() -> None:
    log.info("=== Streamlit keep-alive starting ===")
    driver = build_driver()
    try:
        wake_app(driver)
        log.info("=== Keep-alive ping completed successfully ===")
    except Exception as exc:
        log.error("Keep-alive failed: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
