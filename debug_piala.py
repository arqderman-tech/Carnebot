import sys
sys.path.insert(0, '.')
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36")
    page.goto("https://www.piala.com.ar/productos/", wait_until="networkidle", timeout=30000)
    html = page.content()
    browser.close()

matches = re.findall(r'<li class="product[^"]*">.{0,300}', html, re.DOTALL)
print(f"li.product encontrados: {len(matches)}")
for m in matches[:2]:
    print(m[:200])

soup = BeautifulSoup(html, "lxml")
h3s = soup.find_all("h3")
print(f"\nh3 encontrados: {len(h3s)}")
for h3 in h3s[:3]:
    print(repr(h3))

with open("piala_debug.html", "w") as f:
    f.write(html)
print(f"\nHTML total: {len(html)} chars")
