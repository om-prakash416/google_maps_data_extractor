import os
import re
import gc
import time
import urllib.parse
import threading
import requests
import urllib3
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Suppress SSL warnings for fast website email extraction
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def extract_website_details(url):
    details = {
        "Emails": "N/A",
        "Facebook": "N/A",
        "Instagram": "N/A",
        "LinkedIn": "N/A",
        "YouTube": "N/A"
    }
    if not url or url == "N/A" or not url.startswith(('http://', 'https://')):
        return details
        
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36'}
        with requests.get(url, headers=headers, timeout=(1.0, 2.0), verify=False, stream=True) as response:
            if response.status_code == 200:
                raw_bytes = bytearray()
                for chunk in response.iter_content(chunk_size=4096):
                    raw_bytes.extend(chunk)
                    if len(raw_bytes) > 65536:  # Read max 64 KB
                        break
                html_text = raw_bytes.decode('utf-8', errors='ignore')
                soup = BeautifulSoup(html_text, 'html.parser')
                text_content = soup.get_text(separator=' ')
                
                # Extract Emails using Regex
                emails = set(re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text_content))
                if emails:
                    valid_emails = [
                        e for e in emails 
                        if not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.css', '.js', '.svg'))
                    ]
                    if valid_emails:
                        details["Emails"] = ", ".join(list(valid_emails)[:3])
                        
                # Extract Social Links
                for link in soup.find_all('a', href=True):
                    href = link['href'].lower()
                    if 'facebook.com' in href and details["Facebook"] == "N/A":
                        details["Facebook"] = link['href']
                    elif 'instagram.com' in href and details["Instagram"] == "N/A":
                        details["Instagram"] = link['href']
                    elif 'linkedin.com' in href and details["LinkedIn"] == "N/A":
                        details["LinkedIn"] = link['href']
                    elif 'youtube.com' in href and details["YouTube"] == "N/A":
                        details["YouTube"] = link['href']
    except Exception:
        pass
        
    return details


class ScraperEngine:
    def __init__(self, headless=True):
        self.headless = headless

    def run(self, query, area, radius="", max_results=20, max_threads=1, 
            proxy=None, log_callback=None, data_callback=None, stop_check=None, pincode=""):
        
        queries = [q.strip() for q in query.split(",") if q.strip()]
        areas = [a.strip() for a in area.split(",") if a.strip()]
            
        scraped_data = []
        seen_urls = set()
        
        def safe_log(msg):
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    pass

        def is_stopped():
            if stop_check and stop_check():
                return True
            return False

        safe_log(f"🚀 Starting scraper with queries: {queries} across areas: {areas}")

        for current_query in queries:
            if is_stopped():
                break

            for current_area in areas:
                if is_stopped():
                    break
                if len(scraped_data) >= max_results:
                    break

                safe_log(f"🌐 Starting search for: '{current_query}' in '{current_area}'...")

                browser = None
                context = None
                page = None

                try:
                    with sync_playwright() as p:
                        # Clean production flags (REMOVED --single-process to eliminate TargetClosedError & CancelledError crashes)
                        launch_args = [
                            '--no-sandbox',
                            '--disable-setuid-sandbox',
                            '--disable-dev-shm-usage',
                            '--disable-gpu',
                            '--disable-software-rasterizer',
                            '--disable-extensions',
                            '--no-first-run',
                            '--disable-background-networking',
                            '--disable-background-timer-throttling',
                            '--disable-backgrounding-occluded-windows',
                            '--disable-breakpad',
                            '--disable-client-side-phishing-detection',
                            '--disable-component-update',
                            '--disable-default-apps',
                            '--disable-domain-reliability',
                            '--disable-features=AudioServiceOutOfProcess',
                            '--disable-ipc-flooding-protection',
                            '--disable-notifications',
                            '--disable-popup-blocking',
                            '--disable-print-preview',
                            '--disable-renderer-backgrounding',
                            '--disable-sync',
                            '--hide-scrollbars',
                            '--mute-audio',
                            '--no-default-browser-check',
                            '--no-pings',
                            '--password-store=basic',
                            '--use-gl=swiftshader',
                            '--js-flags=--max-old-space-size=256'
                        ]
                        
                        browser_options = {
                            "headless": self.headless,
                            "args": launch_args
                        }
                        
                        if proxy:
                            browser_options["proxy"] = {"server": proxy}
                            safe_log(f"🛡️ Using proxy for {current_area}")
                            
                        browser = p.chromium.launch(**browser_options)
                        
                        desktop_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                        context = browser.new_context(
                            locale="en-US",
                            user_agent=desktop_ua,
                            viewport={"width": 800, "height": 600}
                        )
                        
                        # Abort heavy media requests to conserve RAM and bandwidth
                        def handle_route(route):
                            try:
                                req_url = route.request.url.lower()
                                if (route.request.resource_type in ["image", "media", "font"] or 
                                    "google-analytics" in req_url or 
                                    "doubleclick" in req_url or 
                                    "/vt/data=" in req_url or 
                                    "play.google.com" in req_url or 
                                    "streetviewpixels" in req_url):
                                    route.abort()
                                else:
                                    route.continue_()
                            except Exception:
                                pass

                        context.route("**/*", handle_route)
                        page = context.new_page()
                        page.set_default_timeout(25000)
                        
                        search_term = f"{current_query} in {current_area}".strip()
                        if pincode and str(pincode).strip():
                            p_clean = str(pincode).strip()
                            if p_clean not in current_area:
                                search_term += f" {p_clean}"
                            
                        encoded_query = urllib.parse.quote(search_term)
                        search_url = f"https://www.google.com/maps/search/{encoded_query}"
                        
                        safe_log(f"🔍 Searching: '{search_term}'")
                        try:
                            page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                        except Exception as e:
                            safe_log(f"⚠️ Page load notice: {str(e)[:80]}")
                        
                        # Handle Google consent popup
                        try:
                            for btn_text in ["Accept all", "I agree", "Accept", "Reject all"]:
                                btn = page.query_selector(f'button:has-text("{btn_text}")')
                                if btn:
                                    btn.click()
                                    time.sleep(1.0)
                                    break
                            if "consent.google.com" in page.url:
                                page.goto(search_url, wait_until='domcontentloaded', timeout=25000)
                        except Exception:
                            pass
                        
                        safe_log(f"⏳ Waiting for results for '{search_term}'...")
                        try:
                            page.wait_for_selector('div[role="feed"], a[href*="/maps/place/"], div[aria-label*="Results"]', timeout=20000)
                        except Exception:
                            safe_log(f"⚠️ No results container found for '{search_term}'. Moving to next.")
                            continue
                            
                        previous_count = 0
                        scroll_attempts = 0
                        
                        safe_log(f"🔄 Scrolling results for '{search_term}'...")
                        while scroll_attempts < 12:
                            if is_stopped():
                                break
                                
                            try:
                                current_count = page.evaluate("() => document.querySelectorAll('a[href*=\"/maps/place/\"]').length")
                            except Exception:
                                current_count = 0
                            
                            needed = max_results - len(scraped_data)
                            if current_count >= needed:
                                break
                                
                            if current_count == previous_count:
                                try:
                                    page.evaluate("document.querySelector('div[role=\"feed\"]').scrollBy(0, 10000)")
                                except Exception:
                                    try:
                                        page.mouse.wheel(0, 5000)
                                    except Exception:
                                        pass
                                time.sleep(1.0)
                                scroll_attempts += 1
                            else:
                                scroll_attempts = 0
                                previous_count = current_count
                                try:
                                    page.evaluate("document.querySelector('div[role=\"feed\"]').scrollBy(0, 10000)")
                                except Exception:
                                    pass
                                time.sleep(0.8)

                        # Extract all place URLs and Names using in-browser JS evaluation
                        places_to_scrape = page.evaluate("""() => {
                            const links = Array.from(document.querySelectorAll('a[href*="/maps/place/"]'));
                            const results = [];
                            const seen = new Set();
                            for (const link of links) {
                                const href = link.href;
                                const name = link.getAttribute('aria-label') || link.innerText.trim();
                                if (href && name && !seen.has(href)) {
                                    seen.add(href);
                                    results.push({ name: name, url: href });
                                }
                            }
                            return results;
                        }""")
                        
                        safe_log(f"⭐ Found {len(places_to_scrape)} listings for '{current_area}'! Extracting details...")
                        if len(places_to_scrape) < needed:
                            safe_log(f"ℹ️ Note: Google Maps has only {len(places_to_scrape)} total listings for this search. (Tip: Add sub-areas/localities to reach {max_results}+).")
                        
                        for p_info in places_to_scrape:
                            if len(scraped_data) >= max_results:
                                break
                            if is_stopped():
                                break
                                
                            try:
                                place_url = p_info.get('url', '')
                                name = p_info.get('name', 'N/A')
                                if not place_url:
                                    continue
                                
                                base_url = place_url.split('?')[0].split('/data=')[0]
                                if base_url in seen_urls:
                                    continue
                                seen_urls.add(base_url)

                                # Fast direct navigation to place details
                                try:
                                    page.goto(place_url, wait_until='domcontentloaded', timeout=15000)
                                except Exception:
                                    pass
                                    
                                time.sleep(0.5)
                                
                                current_url = page.url
                                lat, lon = "", ""
                                coord_match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', current_url)
                                if coord_match:
                                    lat, lon = coord_match.group(1), coord_match.group(2)
                                else:
                                    coord_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', current_url)
                                    if coord_match:
                                        lat, lon = coord_match.group(1), coord_match.group(2)

                                address, phone, website = "N/A", "N/A", "N/A"
                                
                                address_element = page.query_selector('button[data-item-id="address"]')
                                if address_element:
                                    raw_addr = address_element.inner_text().replace('\n', ' ').strip()
                                    address = re.sub(r'[\ue000-\uf8ff]', '', raw_addr).strip()
                                    
                                # Pincode strict filter if specified
                                if pincode and str(pincode).strip():
                                    p_str = str(pincode).strip()
                                    found_pins = re.findall(r'\b\d{6}\b', address)
                                    if found_pins and p_str not in found_pins:
                                        continue
                                
                                phone_element = page.query_selector('button[data-item-id^="phone:"]')
                                if phone_element:
                                    raw_phone = phone_element.inner_text().strip().replace('\n', '')
                                    phone = re.sub(r'[\ue000-\uf8ff]', '', raw_phone).strip()

                                website_element = page.query_selector('a[data-item-id="authority"]')
                                if website_element:
                                    website = website_element.get_attribute('href')
                                    
                                extra_details = extract_website_details(website)

                                item_record = {
                                    "Name": name,
                                    "Search Category": current_query,
                                    "Area": current_area,
                                    "Address": address,
                                    "Phone": phone,
                                    "Website": website,
                                    "Emails": extra_details["Emails"],
                                    "Facebook": extra_details["Facebook"],
                                    "Instagram": extra_details["Instagram"],
                                    "LinkedIn": extra_details["LinkedIn"],
                                    "YouTube": extra_details["YouTube"],
                                    "Latitude": lat,
                                    "Longitude": lon,
                                    "Maps URL": current_url
                                }

                                scraped_data.append(item_record)
                                safe_log(f"   [{len(scraped_data)}/{max_results}] Extracted: {name}")

                                # Realtime streaming callback to UI table
                                if data_callback:
                                    try:
                                        data_callback(item_record)
                                    except Exception:
                                        pass
                                    
                                # Clean garbage regularly to maintain low memory
                                if len(scraped_data) % 5 == 0:
                                    gc.collect()
                                
                            except Exception as item_err:
                                # Log and continue to next item instead of crashing whole search
                                continue

                except Exception as area_err:
                    safe_log(f"⚠️ Notice for '{current_area}': {str(area_err)}")
                finally:
                    # Clean up browser and context cleanly
                    if context:
                        try:
                            context.close()
                        except Exception:
                            pass
                    if browser:
                        try:
                            browser.close()
                        except Exception:
                            pass
                    gc.collect()

        if is_stopped():
            safe_log("🛑 Scraping stopped by user signal.")
        else:
            safe_log(f"✅ Scraping completed! Total {len(scraped_data)} results.")
            
        return scraped_data
