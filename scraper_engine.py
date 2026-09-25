from playwright.sync_api import sync_playwright
import time
import re
import urllib.parse
import uuid
import os
import requests
import urllib3
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import gc

# Suppress SSL warnings for fast website email extraction
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def extract_website_details(url):
    details = {"Emails": "N/A", "Facebook": "N/A", "Instagram": "N/A", "LinkedIn": "N/A", "YouTube": "N/A"}
    if not url or url == "N/A" or not url.startswith(('http://', 'https://')):
        return details
        
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36'}
        with requests.get(url, headers=headers, timeout=1.0, verify=False, stream=True) as response:
            if response.status_code == 200:
                raw_bytes = bytearray()
                for chunk in response.iter_content(chunk_size=4096):
                    raw_bytes.extend(chunk)
                    if len(raw_bytes) > 65536: # read max 64 KB
                        break
                html_text = raw_bytes.decode('utf-8', errors='ignore')
                soup = BeautifulSoup(html_text, 'html.parser')
                text_content = soup.get_text(separator=' ')
                
                # Extract Emails using Regex
                emails = set(re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text_content))
                if emails:
                    valid_emails = [e for e in emails if not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.css', '.js', '.svg'))]
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

    def run(self, query, area, radius, max_results, max_threads=2, proxy=None, log_callback=None, stop_check=None, pincode=""):
        queries = [q.strip() for q in query.split(",") if q.strip()]
        areas = [a.strip() for a in area.split(",") if a.strip()]
            
        scraped_data = []
        seen_urls = set()
        data_lock = threading.Lock()
        
        # Strictly limit to 1 thread in cloud environments to prevent running out of 512MB RAM
        max_threads = 1
        
        def safe_log(msg):
            if log_callback:
                log_callback(msg)
                
        def scrape_task(current_query, current_area):
            if stop_check and stop_check():
                return
                
            browser = None
            context = None
            try:
                with sync_playwright() as p:
                    safe_log(f"🌐 Thread started for: {current_query} near {current_area}...")
                    
                    launch_args = [
                        '--no-sandbox', 
                        '--disable-setuid-sandbox', 
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-software-rasterizer',
                        '--disable-extensions',
                        '--no-first-run',
                        '--no-zygote',
                        '--single-process',
                        '--disable-background-networking',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-breakpad',
                        '--disable-client-side-phishing-detection',
                        '--disable-component-update',
                        '--disable-default-apps',
                        '--disable-domain-reliability',
                        '--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process',
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
                        '--js-flags=--max-old-space-size=128'
                    ]
                    
                    browser_options = {
                        "headless": self.headless,
                        "args": launch_args
                    }
                    
                    if proxy:
                        browser_options["proxy"] = {"server": proxy}
                        safe_log(f"🛡️ Using proxy for {current_area}")
                        
                    browser = p.chromium.launch(**browser_options)
                    
                    desktop_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    context = browser.new_context(
                        locale="en-US", 
                        user_agent=desktop_ua,
                        viewport={"width": 800, "height": 600}
                    )
                    
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
                    
                    search_term = f"{current_query} in {current_area}".strip()
                    if pincode and str(pincode).strip():
                        search_term += f" {str(pincode).strip()}"
                        
                    encoded_query = urllib.parse.quote(search_term)
                    search_url = f"https://www.google.com/maps/search/{encoded_query}"
                    
                    safe_log(f"🔍 Searching: '{search_term}'")
                    page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                    
                    # Handle Google consent popup
                    try:
                        if "consent.google.com" in page.url or page.query_selector('button:has-text("Accept all"), button:has-text("I agree")'):
                            for btn_text in ["Accept all", "I agree", "Accept", "Reject all"]:
                                btn = page.query_selector(f'button:has-text("{btn_text}")')
                                if btn:
                                    btn.click()
                                    time.sleep(1.5)
                                    break
                            if "consent.google.com" in page.url:
                                page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                    except Exception:
                        pass
                    
                    safe_log(f"⏳ Waiting for results for '{search_term}'...")
                    try:
                        page.wait_for_selector('div[role="feed"], a[href*="/maps/place/"], div[aria-label*="Results"]', timeout=20000)
                    except Exception:
                        safe_log(f"❌ Could not find results for '{search_term}'.")
                        return
                        
                    previous_count = 0
                    scroll_attempts = 0
                    place_elements = []
                    
                    safe_log(f"🔄 Scrolling results for '{search_term}'...")
                    while scroll_attempts < 12:
                        if stop_check and stop_check():
                            break
                            
                        place_elements = page.locator('a[href*="/maps/place/"]').all()
                        
                        with data_lock:
                            if len(scraped_data) >= max_results:
                                break
                        
                        if len(place_elements) >= max_results + 5:
                            break
                        
                        if len(place_elements) == previous_count:
                            try:
                                page.hover('div[role="feed"]')
                            except Exception:
                                pass
                            try:
                                page.evaluate("document.querySelector('div[role=\"feed\"]').scrollBy(0, 15000)")
                            except Exception:
                                page.mouse.wheel(0, 5000)
                            time.sleep(1.2)
                            scroll_attempts += 1
                        else:
                            scroll_attempts = 0
                            previous_count = len(place_elements)
                            
                    safe_log(f"⭐ Extracting up to {min(len(place_elements), max_results)} listings from '{search_term}'...")
                    
                    for idx, element in enumerate(place_elements):
                        with data_lock:
                            if len(scraped_data) >= max_results:
                                break
                                
                        if stop_check and stop_check():
                            break
                            
                        try:
                            url = element.get_attribute('href')
                            if not url:
                                continue
                            
                            base_url = url.split('?')[0].split('/data=')[0]
                            with data_lock:
                                if base_url in seen_urls:
                                    continue
                                seen_urls.add(base_url)

                            # Fast, non-blocking click: Scroll & JS click to avoid Playwright 30s actionability timeout
                            try:
                                element.scroll_into_view_if_needed(timeout=600)
                                element.click(timeout=1000, force=True)
                            except Exception:
                                try:
                                    element.evaluate("el => el.click()")
                                except Exception:
                                    continue
                                    
                            time.sleep(0.8)
                            
                            name = element.get_attribute('aria-label') or "N/A"
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
                            
                            try:
                                page.wait_for_selector('button[data-item-id="address"]', timeout=800)
                            except:
                                pass
                            
                            address_element = page.query_selector('button[data-item-id="address"]')
                            if address_element:
                                address = address_element.inner_text().strip()
                                
                            if pincode and str(pincode).strip():
                                p_str = str(pincode).strip()
                                found_pins = re.findall(r'\b\d{6}\b', address)
                                if found_pins and p_str not in found_pins:
                                    continue
                            
                            phone_element = page.query_selector('button[data-item-id^="phone:"]')
                            if phone_element:
                                phone = phone_element.inner_text().strip().replace('\n', '')

                            website_element = page.query_selector('a[data-item-id="authority"]')
                            if website_element:
                                website = website_element.get_attribute('href')
                                
                            extra_details = extract_website_details(website)

                            with data_lock:
                                scraped_data.append({
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
                                })
                                safe_log(f"   [{len(scraped_data)}/{max_results}] Extracted: {name}")
                                
                                # Garbage collect every 2 items to prevent memory build-up in 512MB RAM
                                if len(scraped_data) % 2 == 0:
                                    gc.collect()
                            
                        except Exception:
                            pass
                            
            except Exception as e:
                safe_log(f"❌ Thread Error for '{current_area}': {str(e)}")
            finally:
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

        # Execute using ThreadPool
        safe_log(f"🚀 Starting Engine with max {max_threads} concurrent thread(s)...")
        tasks = []
        for current_query in queries:
            for current_area in areas:
                tasks.append((current_query, current_area))
                
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = []
            for task in tasks:
                futures.append(executor.submit(scrape_task, task[0], task[1]))
                
            for future in as_completed(futures):
                pass 
                
        safe_log("✅ All tasks completed!")
        return scraped_data

