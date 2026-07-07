import customtkinter as ctk
import tkinter.filedialog as fd
import tkinter.messagebox as mb
import csv
from playwright.sync_api import sync_playwright
import threading
import queue
import time
import re
import os

try:
    import pandas as pd
except ImportError:
    pd = None

# Set UI appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ScraperApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Google Maps Data Extractor (Pro Version)")
        self.geometry("900x650")
        self.minsize(800, 600)
        
        self.log_queue = queue.Queue()
        self.is_stopped = False
        self.scraped_data = []
        
        # --- UI LAYOUT ---
        # Grid Configuration
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # --- SIDEBAR (Left) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color="#1a1a2e")
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(7, weight=1)
        
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="📍 GMaps Extractor", font=ctk.CTkFont(size=24, weight="bold"), text_color="#e94560")
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        self.subtitle = ctk.CTkLabel(self.sidebar_frame, text="Extract ANY business data", text_color="gray", font=ctk.CTkFont(size=12))
        self.subtitle.grid(row=1, column=0, padx=20, pady=(0, 20))

        # Inputs
        self.query_entry = ctk.CTkEntry(self.sidebar_frame, placeholder_text="e.g. Restaurants", width=250, height=40, corner_radius=8)
        self.query_entry.grid(row=2, column=0, padx=20, pady=10)
        
        self.area_entry = ctk.CTkEntry(self.sidebar_frame, placeholder_text="Area (e.g. Delhi)", width=250, height=40, corner_radius=8)
        self.area_entry.grid(row=3, column=0, padx=20, pady=10)
        
        self.radius_entry = ctk.CTkEntry(self.sidebar_frame, placeholder_text="Radius (km) - Optional", width=250, height=40, corner_radius=8)
        self.radius_entry.grid(row=4, column=0, padx=20, pady=10)
        
        self.count_entry = ctk.CTkEntry(self.sidebar_frame, placeholder_text="Max Results (e.g. 50)", width=250, height=40, corner_radius=8)
        self.count_entry.insert(0, "20")
        self.count_entry.grid(row=5, column=0, padx=20, pady=10)
        
        # Action Buttons
        self.start_btn = ctk.CTkButton(self.sidebar_frame, text="▶ Start Scraping", command=self.start_scraping_thread, height=45, width=250, corner_radius=8, font=ctk.CTkFont(weight="bold", size=15), fg_color="#0f3460", hover_color="#1a1a2e")
        self.start_btn.grid(row=6, column=0, padx=20, pady=(20, 10))
        
        self.stop_btn = ctk.CTkButton(self.sidebar_frame, text="⏹ Stop", command=self.stop_scraping, height=45, width=250, corner_radius=8, font=ctk.CTkFont(weight="bold", size=15), fg_color="#e94560", hover_color="#c81d3d", state="disabled")
        self.stop_btn.grid(row=7, column=0, padx=20, pady=(0, 20), sticky="n")

        # Footer
        self.footer_label = ctk.CTkLabel(self.sidebar_frame, text="Made by Om Prakash\n(GitHub: om-prakash416)", font=ctk.CTkFont(size=12, weight="bold"), text_color="#0f3460")
        self.footer_label.grid(row=8, column=0, padx=20, pady=20, sticky="s")

        # --- MAIN AREA (Right) ---
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        
        # Progress & Status
        self.status_frame = ctk.CTkFrame(self.main_frame, fg_color="#16213e", corner_radius=10)
        self.status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        
        self.status_label = ctk.CTkLabel(self.status_frame, text="Status: Ready", font=ctk.CTkFont(size=16, weight="bold"), text_color="#43d590")
        self.status_label.pack(side="left", padx=20, pady=15)
        
        self.progress = ctk.CTkProgressBar(self.status_frame, mode="indeterminate", width=300, height=10, progress_color="#e94560")
        self.progress.pack(side="right", padx=20, pady=15)
        self.progress.set(0)

        # Logs Console
        self.log_box = ctk.CTkTextbox(self.main_frame, state="disabled", corner_radius=10, fg_color="#0f3460", text_color="#ffffff", font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.grid(row=1, column=0, sticky="nsew")

        # Export Frame
        self.export_frame = ctk.CTkFrame(self.main_frame, fg_color="#16213e", corner_radius=10)
        self.export_frame.grid(row=2, column=0, sticky="ew", pady=(20, 0))
        
        self.export_label = ctk.CTkLabel(self.export_frame, text="Download Results:", font=ctk.CTkFont(size=16, weight="bold"))
        self.export_label.pack(side="left", padx=20, pady=15)
        
        self.btn_csv = ctk.CTkButton(self.export_frame, text="📄 CSV", width=100, height=35, command=lambda: self.export_data('csv'), state="disabled", fg_color="#333333", hover_color="#555555")
        self.btn_csv.pack(side="left", padx=10)
        
        self.btn_xlsx = ctk.CTkButton(self.export_frame, text="📊 XLSX", width=100, height=35, command=lambda: self.export_data('xlsx'), state="disabled", fg_color="#217346", hover_color="#1e5c3a")
        self.btn_xlsx.pack(side="left", padx=10)
        
        self.btn_xls = ctk.CTkButton(self.export_frame, text="📉 XLS", width=100, height=35, command=lambda: self.export_data('xls'), state="disabled", fg_color="#107c41", hover_color="#0b5e31")
        self.btn_xls.pack(side="left", padx=10)
        
        # Setup polling for logs
        self.check_queue()

    def update_status(self, text, color="#43d590"):
        self.status_label.configure(text=text, text_color=color)

    def set_export_buttons_state(self, state):
        self.btn_csv.configure(state=state)
        self.btn_xlsx.configure(state=state)
        self.btn_xls.configure(state=state)

    def export_data(self, format_type):
        if not self.scraped_data:
            mb.showerror("Error", "No data to save!")
            return
            
        filetypes = []
        defaultext = ""
        if format_type == 'csv':
            filetypes = [('CSV Files', '*.csv')]
            defaultext = ".csv"
        elif format_type == 'xlsx':
            filetypes = [('Excel Files (XLSX)', '*.xlsx')]
            defaultext = ".xlsx"
        elif format_type == 'xls':
            filetypes = [('Excel Files (XLS)', '*.xls')]
            defaultext = ".xls"
            
        filepath = fd.asksaveasfilename(defaultextension=defaultext, filetypes=filetypes, title=f"Save as {format_type.upper()}")
        
        if not filepath:
            return
            
        try:
            if format_type == 'csv':
                keys = self.scraped_data[0].keys()
                with open(filepath, 'w', newline='', encoding='utf-8') as output_file:
                    dict_writer = csv.DictWriter(output_file, fieldnames=keys)
                    dict_writer.writeheader()
                    dict_writer.writerows(self.scraped_data)
            else:
                if pd is None:
                    mb.showerror("Error", "pandas library is required for Excel export. Please run 'pip install pandas openpyxl xlwt' in your terminal.")
                    return
                df = pd.DataFrame(self.scraped_data)
                df.to_excel(filepath, index=False)
                
            self.log(f"✅ Data successfully saved to:\n{filepath}")
            mb.showinfo("Success", f"Data saved to {filepath}")
        except Exception as e:
            self.log(f"❌ Error saving file: {e}")
            mb.showerror("Error", f"Could not save file: {e}")

    def log(self, message):
        self.log_queue.put(message)

    def check_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(100, self.check_queue)

    def stop_scraping(self):
        self.log("🛑 Stopping... Please wait for the current item to finish.")
        self.update_status("Status: Stopping...", color="#e94560")
        self.is_stopped = True
        self.stop_btn.configure(state="disabled")

    def start_scraping_thread(self):
        query = self.query_entry.get().strip()
        area = self.area_entry.get().strip()
        count_str = self.count_entry.get().strip()
        radius_str = self.radius_entry.get().strip()
        
        if not query or not area or not count_str.isdigit():
            self.log("❌ Please fill Query, Area, and Max Results.")
            return
            
        max_results = int(count_str)
        search_term = f"{query} near {area}"
        if radius_str and radius_str.isdigit():
            search_term += f" within {radius_str} km"
        
        self.is_stopped = False
        self.scraped_data = []
        self.set_export_buttons_state("disabled")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.start()
        self.log(f"🚀 Started! Searching for: '{search_term}'")
        self.update_status("Status: Scraping...", color="#e94560")
        
        threading.Thread(target=self.run_scraper, args=(search_term, max_results, area, query), daemon=True).start()

    def run_scraper(self, search_term, max_results, area, query):
        try:
            data = self.scrape_google_maps(search_term, max_results)
            self.scraped_data = data
            if data:
                self.log(f"✅ Extracted {len(data)} items. You can now download the data.")
                self.after(0, lambda: self.set_export_buttons_state("normal"))
            else:
                self.log("⚠️ No data was found or extracted.")
        except Exception as e:
            self.log(f"❌ Error occurred: {str(e)}")
        finally:
            self.after(0, lambda: self.start_btn.configure(state="normal"))
            self.after(0, lambda: self.stop_btn.configure(state="disabled"))
            self.after(0, lambda: self.progress.stop())
            self.after(0, lambda: self.progress.set(0))
            self.after(0, lambda: self.update_status("Status: Completed", color="#43d590"))

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
                        "Search Category": search_query.split(" in ")[0] if " in " in search_query else search_query,
                        "Area": search_query.split(" near ")[1].split(" within ")[0] if " near " in search_query else "N/A",
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
