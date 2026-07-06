import customtkinter as ctk
import csv
from playwright.sync_api import sync_playwright
import threading
import queue
import time
import re
import os

# Set UI appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ScraperApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Google Maps Data Extractor (Pro Version)")
        self.geometry("650x650")
        
        self.log_queue = queue.Queue()
        self.is_stopped = False
        
        # --- UI ELEMENTS ---
        self.title_label = ctk.CTkLabel(self, text="📍 Google Maps Data Extractor", font=ctk.CTkFont(size=26, weight="bold"))
        self.title_label.pack(pady=(20, 10))
        
        self.subtitle = ctk.CTkLabel(self, text="Extract ANY business data for free straight into Excel.", text_color="gray")
        self.subtitle.pack(pady=(0, 20))

        # Main Input Frame
        self.query_frame = ctk.CTkFrame(self)
        self.query_frame.pack(pady=10, padx=20, fill="x")
        
        # Query
        self.query_label = ctk.CTkLabel(self.query_frame, text="What do you want to search? (e.g., Saloons, Plumbers, Gyms):", font=ctk.CTkFont(weight="bold"))
        self.query_label.pack(anchor="w", padx=15, pady=(15, 0))
        self.query_entry = ctk.CTkEntry(self.query_frame, placeholder_text="e.g. Restaurants")
        self.query_entry.pack(fill="x", padx=15, pady=(5, 10))

        # Area
        self.area_label = ctk.CTkLabel(self.query_frame, text="Area / Location (e.g., Bandra, Mumbai):", font=ctk.CTkFont(weight="bold"))
        self.area_label.pack(anchor="w", padx=15)
        self.area_entry = ctk.CTkEntry(self.query_frame, placeholder_text="e.g. Connaught Place, Delhi")
        self.area_entry.pack(fill="x", padx=15, pady=(5, 10))

        # Radius (Optional)
        self.radius_label = ctk.CTkLabel(self.query_frame, text="Radius in km (Optional, e.g., 5):", font=ctk.CTkFont(weight="bold"))
        self.radius_label.pack(anchor="w", padx=15)
        self.radius_entry = ctk.CTkEntry(self.query_frame, placeholder_text="Leave empty for default area size")
        self.radius_entry.pack(fill="x", padx=15, pady=(5, 10))

        # Count
        self.count_label = ctk.CTkLabel(self.query_frame, text="Max Results to Extract:", font=ctk.CTkFont(weight="bold"))
        self.count_label.pack(anchor="w", padx=15)
        self.count_entry = ctk.CTkEntry(self.query_frame, placeholder_text="e.g. 50")
        self.count_entry.insert(0, "20")
        self.count_entry.pack(fill="x", padx=15, pady=(5, 15))
        
        # Buttons Frame
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=15)
        
        self.start_btn = ctk.CTkButton(self.btn_frame, text="Start Scraping Data", command=self.start_scraping_thread, height=45, font=ctk.CTkFont(size=16, weight="bold"))
        self.start_btn.pack(side="left", padx=5)
        
        self.stop_btn = ctk.CTkButton(self.btn_frame, text="Stop & Save", command=self.stop_scraping, height=45, font=ctk.CTkFont(size=16, weight="bold"), fg_color="#D9534F", hover_color="#C9302C", state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        # Progress Bar
        self.progress = ctk.CTkProgressBar(self, mode="indeterminate", height=8, progress_color="#00FF00")
        self.progress.pack(padx=20, pady=(10, 5), fill="x")
        self.progress.set(0)

        # Logs Console
        self.log_label = ctk.CTkLabel(self, text="Activity Log:", font=ctk.CTkFont(weight="bold"))
        self.log_label.pack(anchor="w", padx=20)
        self.log_box = ctk.CTkTextbox(self, state="disabled", height=150, fg_color="#1E1E1E", text_color="#00FF00")
        self.log_box.pack(pady=(5, 20), padx=20, fill="both", expand=True)

        # Setup polling for logs
        self.check_queue()

    def log(self, message):
        """Thread-safe logging function"""
        self.log_queue.put(message)

    def check_queue(self):
        """Polls the queue to safely update UI from the background thread"""
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(100, self.check_queue)

    def stop_scraping(self):
        self.log("🛑 Stop button clicked! Saving extracted data...")
        self.is_stopped = True
        self.stop_btn.configure(state="disabled", text="Stopping...")

    def start_scraping_thread(self):
        query = self.query_entry.get().strip()
        area = self.area_entry.get().strip()
        count_str = self.count_entry.get().strip()
        radius_str = self.radius_entry.get().strip()
        
        if not query or not area or not count_str.isdigit():
            self.log("❌ Please fill all fields correctly. Max Results must be a number.")
            return
            
        max_results = int(count_str)
        search_term = f"{query} near {area}"
        if radius_str and radius_str.isdigit():
            search_term += f" within {radius_str} km"
        
        self.is_stopped = False
        self.start_btn.configure(state="disabled", text="Scraping in progress...")
        self.stop_btn.configure(state="normal", text="Stop & Save")
        self.progress.start()
        self.log(f"🚀 Started! Searching for: '{search_term}'")
        
        # Run scraper in a background thread to prevent UI freezing
        threading.Thread(target=self.run_scraper, args=(search_term, max_results, area, query), daemon=True).start()

    def run_scraper(self, search_term, max_results, area, query):
        try:
            data = self.scrape_google_maps(search_term, max_results)
            if data:
                output_dir = os.path.join(os.getcwd(), "output")
                os.makedirs(output_dir, exist_ok=True)
                
                filename = f"{query.replace(' ', '_')}_{area.replace(' ', '_')}_Data.csv"
                filepath = os.path.join(output_dir, filename)
                
                # Use standard python CSV instead of pandas to avoid C++ build tool requirements
                keys = data[0].keys()
                with open(filepath, 'w', newline='', encoding='utf-8') as output_file:
                    dict_writer = csv.DictWriter(output_file, fieldnames=keys)
                    dict_writer.writeheader()
                    dict_writer.writerows(data)
                    
                self.log(f"✅ SUCCESS! Data saved to:\n{filepath}")
            else:
                self.log("⚠️ No data was found or extracted.")
        except Exception as e:
            self.log(f"❌ Error occurred: {str(e)}")
        finally:
            self.start_btn.configure(state="normal", text="Start Scraping Data")
            self.stop_btn.configure(state="disabled", text="Stop & Save")
            self.progress.stop()
            self.progress.set(0)

    def scrape_google_maps(self, search_query, max_results):
        scraped_data = []
        with sync_playwright() as p:
            self.log("🌐 Opening Browser in Background (Hidden)...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US")
            page = context.new_page()
            
            import urllib.parse
            encoded_query = urllib.parse.quote(search_query)
            search_url = f"https://www.google.com/maps/search/{encoded_query}"
            
            self.log("🔍 Loading search results directly...")
            page.goto(search_url, timeout=60000)
            
            self.log("⏳ Waiting for results to load...")
            try:
                page.wait_for_selector('div[role="feed"]', timeout=15000)
            except Exception:
                self.log("❌ Could not find results. Timeout or no results.")
                browser.close()
                return scraped_data

            feed_selector = 'div[role="feed"]'
            previous_count = 0
            scroll_attempts = 0
            
            self.log("🔄 Scrolling to find more listings...")
            while len(scraped_data) < max_results and scroll_attempts < 10:
                if self.is_stopped:
                    self.log("🛑 Scrolling interrupted.")
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
                    self.log(f"   Loaded {previous_count} listings in view...")
                    
                if len(place_elements) >= max_results:
                    break
                    
            self.log(f"⭐ Found {len(place_elements)} listings! Starting data extraction...")
            
            for i, element in enumerate(place_elements[:max_results]):
                if self.is_stopped:
                    self.log("🛑 Data extraction stopped.")
                    break
                    
                try:
                    element.click()
                    time.sleep(2.5) # Wait for details sidebar to load completely
                    
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
                    
                    # Small wait for details to populate
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
                        "Search Category": search_query.split(" in ")[0],
                        "Area": search_query.split(" in ")[1] if " in " in search_query else "N/A",
                        "Address": address,
                        "Phone": phone,
                        "Website": website,
                        "Latitude": lat,
                        "Longitude": lon,
                        "Maps URL": url
                    })
                    
                    self.log(f"   [{i+1}/{max_results}] Extracted: {name}")
                    
                except Exception as e:
                    self.log(f"   [{i+1}/{max_results}] Error extracting item: {e}")
                    continue

            self.log("✅ Extraction Complete! Closing browser...")
            browser.close()
            
        return scraped_data

if __name__ == "__main__":
    app = ScraperApp()
    app.mainloop()
