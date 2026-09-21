from playwright.sync_api import sync_playwright
import time
import re
import urllib.parse
import uuid
import os
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

def extract_website_details(url):
    details = {"Emails": "N/A", "Facebook": "N/A", "Instagram": "N/A", "LinkedIn": "N/A", "YouTube": "N/A"}
    if not url or url == "N/A":
        return details
        
    try:
        headers = {'User-Agent': UserAgent().random}
        response = requests.get(url, headers=headers, timeout=4)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            html_text = soup.get_text(separator=' ')
            
            # Extract Emails using Regex
            emails = set(re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', html_text))
            if emails:
                # Filter out obvious false positives
                valid_emails = [e for e in emails if not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.css', '.js'))]
                if valid_emails:
                    details["Emails"] = ", ".join(valid_emails)
                    
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
        
        def safe_log(msg):
            if log_callback:
                log_callback(msg)
                
        def scrape_task(current_query, current_area):
            if stop_check and stop_check():
                return
                
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
                    
                    # Generate fake user agent
                    ua = UserAgent().random
                    context = browser.new_context(locale="en-US", user_agent=ua)
                    
                    # Block heavy resources to save RAM safely
                    def handle_route(route):
                        try:
                            if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
                                route.abort()
                            else:
                                route.continue_()
                        except Exception:
                            pass

                    context.route("**/*", handle_route)
                    
                    def safe_close_browser():
                        try:
                            context.unroute("**/*")
                        except Exception:
                            pass
                        try:
                            browser.close()
                        except Exception:
                            pass
                    
                    page = context.new_page()
                    
                    search_parts = [current_query, "near", current_area]
                    if pincode and str(pincode).strip():
                        search_parts.append(str(pincode).strip())
                    search_term = " ".join(search_parts).strip()
                        
                    encoded_query = urllib.parse.quote(search_term)
                    search_url = f"https://www.google.com/maps/search/{encoded_query}"
                    
                    safe_log(f"🔍 Searching: '{search_term}'")
                    page.goto(search_url, timeout=60000)
                    
                    safe_log(f"⏳ Waiting for results for '{search_term}'...")
                    try:
                        page.wait_for_selector('div[role="feed"], a[href*="/maps/place/"]', timeout=15000)
                    except Exception:
                        safe_log(f"❌ Could not find results for '{search_term}'.")
                        safe_close_browser()
                        return
                        
                    previous_count = 0
                    scroll_attempts = 0
                    place_elements = []
                    
                    safe_log(f"🔄 Scrolling results for '{search_term}'...")
                    while scroll_attempts < 15:
                        if stop_check and stop_check():
                            break
                            
                        place_elements = page.locator('a[href*="/maps/place/"]').all()
                        
                        with data_lock:
                            if len(scraped_data) >= max_results:
                                break
                        
                        if len(place_elements) >= max_results + 20:
                            break
                        
                        if len(place_elements) == previous_count:
                            try:
                                page.evaluate("document.querySelector('div[role=\"feed\"]').scrollBy(0, 15000)")
                            except Exception:
                                page.mouse.wheel(0, 5000)
                            time.sleep(3)
                            scroll_attempts += 1
                        else:
                            scroll_attempts = 0
                            previous_count = len(place_elements)
                            
                    safe_log(f"⭐ Extracting {len(place_elements)} listings from '{search_term}'...")
                    
                    for element in place_elements:
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

                            element.click()
                            time.sleep(2.5)
                            
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
                                page.wait_for_selector('button[data-item-id="address"]', timeout=3000)
                            except:
                                pass
                            
                            address_element = page.query_selector('button[data-item-id="address"]')
                            if address_element:
                                address = address_element.inner_text().strip()
                                
                            if pincode and pincode not in address:
                                continue
                            
                            phone_element = page.query_selector('button[data-item-id^="phone:"]')
                            if phone_element:
                                phone = phone_element.inner_text().strip().replace('\n', '')

                            website_element = page.query_selector('a[data-item-id="authority"]')
                            if website_element:
                                website = website_element.get_attribute('href')
                                
                            # Extract extra details from website
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
                            
                        except Exception as e:
                            pass
                            
                    safe_close_browser()
                    
            except Exception as e:
                safe_log(f"❌ Thread Error for '{current_area}': {str(e)}")

        # Execute using ThreadPool
        safe_log(f"🚀 Starting Engine with {max_threads} Threads...")
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
