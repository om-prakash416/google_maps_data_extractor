import pandas as pd
from playwright.sync_api import sync_playwright
import time
import re

def scrape_saloons(area_name, max_results=50):
    print(f"Searching for Saloons in {area_name}...")
    search_query = f"Saloons in {area_name}"
    scraped_data = []

    with sync_playwright() as p:
        # Launch browser (headless=False so you can see it working)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="en-US")
        page = context.new_page()
        
        # Go to Google Maps
        page.goto("https://www.google.com/maps", timeout=60000)
        
        # Wait for search box and search
        page.wait_for_selector('input#searchboxinput', timeout=10000)
        page.fill('input#searchboxinput', search_query)
        page.press('input#searchboxinput', 'Enter')
        
        # Wait for the results panel to load
        print("Waiting for results to load...")
        try:
            page.wait_for_selector('div[role="feed"]', timeout=15000)
        except Exception:
            print("Could not find the results feed. The area might not have results or page loaded slowly.")
            browser.close()
            return scraped_data

        # Scroll to load more results
        print("Scrolling to fetch more data...")
        feed_selector = 'div[role="feed"]'
        
        # Scroll loop
        previous_count = 0
        scroll_attempts = 0
        
        while len(scraped_data) < max_results and scroll_attempts < 10:
            # Find all place links currently loaded
            place_elements = page.locator('a[href*="/maps/place/"]').all()
            
            if len(place_elements) == previous_count:
                # Try to scroll the feed
                page.hover(feed_selector)
                page.mouse.wheel(0, 2000)
                time.sleep(2)
                scroll_attempts += 1
            else:
                scroll_attempts = 0
                previous_count = len(place_elements)
                
            if len(place_elements) >= max_results:
                break
                
        print(f"Found {len(place_elements)} saloons. Extracting data...")
        
        # Extract data from the found elements
        for i, element in enumerate(place_elements[:max_results]):
            try:
                # Click on the place to load its details in the sidebar
                element.click()
                time.sleep(3) # Wait for details to load
                
                # Extract basic info
                name = element.get_attribute('aria-label') or "N/A"
                url = page.url
                
                # Extract coordinates from URL
                lat, lon = "", ""
                coord_match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
                if coord_match:
                    lat, lon = coord_match.group(1), coord_match.group(2)
                else:
                    coord_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
                    if coord_match:
                        lat, lon = coord_match.group(1), coord_match.group(2)

                # Get address, phone, website from the sidebar
                # Google Maps uses icons for these. We can find buttons by their aria-labels or roles
                address, phone, website = "N/A", "N/A", "N/A"
                
                # Wait a bit for sidebar content to populate
                page.wait_for_selector('button[data-item-id="address"]', timeout=5000)
                
                address_element = page.query_selector('button[data-item-id="address"]')
                if address_element:
                    address = address_element.inner_text().strip()
                
                phone_element = page.query_selector('button[data-item-id^="phone:"]')
                if phone_element:
                    phone = phone_element.inner_text().strip().replace('\n', '')

                website_element = page.query_selector('a[data-item-id="authority"]')
                if website_element:
                    website = website_element.get_attribute('href')

                # Append to our list
                scraped_data.append({
                    "Name": name,
                    "Area": area_name,
                    "City": address.split(',')[-2].strip() if len(address.split(',')) > 1 else "",
                    "State": address.split(',')[-1].strip().split(' ')[0] if len(address.split(',')) > 1 else "",
                    "Full Address": address,
                    "Phone": phone,
                    "Website": website,
                    "Latitude": lat,
                    "Longitude": lon,
                    "Maps URL": url,
                    "Email": "Not available on Google Maps" # Emails are rarely on Google Maps
                })
                
                print(f"Extracted: {name}")
                
            except Exception as e:
                print(f"Error extracting data for an item: {e}")
                continue

        browser.close()
        
    return scraped_data

if __name__ == "__main__":
    area = input("Enter the Area/City to search for Saloons (e.g., 'Connaught Place, Delhi'): ")
    num_results = int(input("How many results do you want to extract? (e.g., 20): "))
    
    data = scrape_saloons(area, max_results=num_results)
    
    if data:
        # Convert to pandas DataFrame and save to Excel
        df = pd.DataFrame(data)
        excel_filename = f"Saloons_{area.replace(' ', '_')}.xlsx"
        df.to_excel(excel_filename, index=False)
        print(f"\n✅ Data successfully saved to {excel_filename}")
    else:
        print("\n❌ No data was found or extracted.")
