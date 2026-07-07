from playwright.sync_api import sync_playwright
import time
import re
import urllib.parse
import uuid
import os

class ScraperEngine:
    def __init__(self, headless=True):
        self.headless = headless

    def run(self, query, area, radius, max_results, log_callback=None, stop_check=None):
        search_term = f"{query} near {area}"
        if radius and str(radius).isdigit():
            search_term += f" within {radius} km"
            
        scraped_data = []
        
        def safe_log(msg):
            if log_callback:
                log_callback(msg)
                
        try:
            with sync_playwright() as p:
                safe_log("🌐 Opening Browser...")
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(locale="en-US")
                page = context.new_page()
                
                encoded_query = urllib.parse.quote(search_term)
                search_url = f"https://www.google.com/maps/search/{encoded_query}"
                
                safe_log(f"🔍 Searching for: '{search_term}'")
                page.goto(search_url, timeout=60000)
                
                safe_log("⏳ Waiting for results to load...")
                try:
                    page.wait_for_selector('div[role="feed"]', timeout=15000)
                except Exception:
                    safe_log("❌ Could not find results. Timeout or no results.")
                    browser.close()
                    return scraped_data

                feed_selector = 'div[role="feed"]'
                previous_count = 0
                scroll_attempts = 0
                
                safe_log("🔄 Scrolling to find more listings...")
                while len(scraped_data) < max_results and scroll_attempts < 10:
                    if stop_check and stop_check():
                        safe_log("🛑 Scrolling interrupted.")
                        break
                        
                    place_elements = page.locator('a[href*="/maps/place/"]').all()
                    
                    if len(place_elements) == previous_count:
                        page.hover(feed_selector)
                        page.mouse.wheel(0, 3000)
                        time.sleep(2)
                        scroll_attempts += 1
                    else:
                        scroll_attempts = 0
                        previous_count = len(place_elements)
                        safe_log(f"   Loaded {previous_count} listings in view...")
                        
                    if len(place_elements) >= max_results:
                        break
                        
                safe_log(f"⭐ Found {len(place_elements)} listings! Extracting data...")
                
                for i, element in enumerate(place_elements[:max_results]):
                    if stop_check and stop_check():
                        safe_log("🛑 Data extraction stopped.")
                        break
                        
                    try:
                        element.click()
                        time.sleep(2.5)
                        
                        name = element.get_attribute('aria-label') or "N/A"
                        url = page.url
                        
                        lat, lon = "", ""
                        coord_match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
                        if coord_match:
                            lat, lon = coord_match.group(1), coord_match.group(2)
                        else:
                            coord_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
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
                        
                        phone_element = page.query_selector('button[data-item-id^="phone:"]')
                        if phone_element:
                            phone = phone_element.inner_text().strip().replace('\n', '')

                        website_element = page.query_selector('a[data-item-id="authority"]')
                        if website_element:
                            website = website_element.get_attribute('href')

                        scraped_data.append({
                            "Name": name,
                            "Search Category": query,
                            "Area": area,
                            "Address": address,
                            "Phone": phone,
                            "Website": website,
                            "Latitude": lat,
                            "Longitude": lon,
                            "Maps URL": url
                        })
                        
                        safe_log(f"   [{i+1}/{max_results}] Extracted: {name}")
                        
                    except Exception as e:
                        safe_log(f"   [{i+1}/{max_results}] Error extracting item: {e}")
                        continue

                safe_log("✅ Extraction Complete! Closing browser...")
                browser.close()
                
        except Exception as e:
            safe_log(f"❌ Critical Error: {str(e)}")
            
        return scraped_data
