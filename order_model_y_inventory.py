# -*- coding: utf-8 -*-
"""
Model Y - Envanter Botu
• Tesla hesabına giriş + (varsa) 2-Aşamalı doğrulama
• https://www.tesla.com/inventory/new/my?... sayfasına git
• Kartlardaki fiyatları okuyup TARGET_PRICE altındaki ilk aracı tıkla
Playwright 1.44  –  pip install playwright==1.44 pyotp python-dotenv
"""

import json, os, re, sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError
from dotenv import load_dotenv
from pyotp import TOTP

# ────────────────────────────────────────────────────────────
# ENV değişkenlerini al
# ────────────────────────────────────────────────────────────
load_dotenv()
EMAIL = os.getenv("TESLA_EMAIL")
PASSWORD = os.getenv("TESLA_PASSWORD")
TOTP_SECRET = os.getenv("TESLA_TOTP")  # 2FA devre dışıysa None
INVENTORY_URL = os.getenv(
    "INVENTORY_URL",
    "https://www.tesla.com/inventory/new/my?arrangeby=savings&zip=26180&range=0"
)
TARGET_PRICE = int(os.getenv("TARGET_PRICE", "0"))  # 0 → sınırsız
LOCALE = os.getenv("LOCALE", "en-US")
HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"


# ────────────────────────────────────────────────────────────
# Yardımcılar
# ────────────────────────────────────────────────────────────
def _int_only(text: str) -> int:
    """'$54,620' ➜ 54620"""
    return int(re.sub(r"[^\d]", "", text))


# ────────────────────────────────────────────────────────────
# Adım 1 – Giriş
# ────────────────────────────────────────────────────────────
def login(page):
    page.goto("https://www.tesla.com/teslaaccount", wait_until="networkidle")
    page.locator('input[name="identity"]').fill(EMAIL)
    page.click('button[type="submit"]')
    page.locator('input[name="credential"]').fill(PASSWORD)
    page.click('button[type="submit"]')

    # 2FA gerekiyorsa:
    if page.locator('input[name="otp"]').is_visible():
        if not TOTP_SECRET:
            raise RuntimeError("2FA açık ama TESLA_TOTP env değişkeni yok!")
        page.locator('input[name="otp"]').fill(TOTP(TOTP_SECRET).now())
        page.click('button[type="submit"]')


# ────────────────────────────────────────────────────────────
# Adım 2 – Envanter taraması & tıklama
# ────────────────────────────────────────────────────────────
def choose_inventory_vehicle(page):
    # page.goto(INVENTORY_URL, wait_until="commit")
    #

    page.goto(INVENTORY_URL, wait_until="commit", timeout=60_000)

    data_json = page.eval_on_selector("#__NEXT_DATA__", "el => el.textContent")


    # 2) HTML gövdesi geldiyse __NEXT_DATA__ mutlaka oluşur
    page.wait_for_selector("#__NEXT_DATA__", timeout=10_000)



    # ① Sayfa React/Next.js; tüm veriler __NEXT_DATA__ JSON’unda.
    data_json = page.evaluate(
        "() => document.querySelector('#__NEXT_DATA__')?.textContent"
    )
    if not data_json:
        raise RuntimeError("Envanter verisi (__NEXT_DATA__) bulunamadı.")

    data = json.loads(data_json)
    try:
        # YOL : props.pageProps.results.vehicles   (2025 Nisan güncel)
        vehicles = data["props"]["pageProps"]["results"]["vehicles"]
    except KeyError:
        raise RuntimeError("JSON yapısı değişti — parser’ı güncelleyin.")

    # ② Fiyat filtresi
    chosen = None
    for v in vehicles:
        price = v.get("PurchasePrice") or v.get("pricing", {}).get("PurchasePrice")
        if price is None:
            continue
        if TARGET_PRICE == 0 or price <= TARGET_PRICE:
            chosen = v
            break

    if not chosen:
        raise RuntimeError(
            f"{TARGET_PRICE}$ altında envanter aracı bulunamadı."
            if TARGET_PRICE else "Hiç araç listesi alınamadı."
        )

    vin = chosen["VIN"]
    order_link = chosen.get("OrderLink") or chosen.get("OrderUrl")
    print(f"Seçilen VIN {vin} — Fiyat: {price}$")

    # ③ Sayfadaki kartı tıkla (href içinde VIN geçen <a> etiketi)
    selector = f'a[href*="{vin.lower()}"]'
    page.locator(selector).first.click()


# ────────────────────────────────────────────────────────────
# Main akış
# ────────────────────────────────────────────────────────────
def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=70)
        context = browser.new_context(locale=LOCALE)
        page = context.new_page()

        try:
            login(page)
            choose_inventory_vehicle(page)
            print("✅ Araç detay sayfasına/Checkout akışına geçildi.")
        except TimeoutError as te:
            print("⛔ Sayfa elemanı bulunamadı ➜", te)
        except Exception as exc:
            print("⛔ Hata ➜", exc)
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    if not (EMAIL and PASSWORD):
        sys.exit("TESLA_EMAIL / TESLA_PASSWORD tanımlı değil!")
    main()
