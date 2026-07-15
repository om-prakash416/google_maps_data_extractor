---
title: Google Maps Data Extractor Pro
emoji: 📍
colorFrom: blue
colorTo: purple
sdk: docker
app_file: app.py
pinned: false
---

# Google Maps Data Extractor 📍

A powerful, modern, and completely free Python desktop application to extract business data from Google Maps and save it directly to CSV.

## ✨ Features
- **Modern UI:** Built with `CustomTkinter` for a sleek, dark-mode graphical interface.
- **Headless Browsing:** Runs Google Chrome silently in the background using `Playwright`.
- **Dynamic Search:** Search for any business type (Saloons, Plumbers, Hospitals, Gyms, etc.) in any Area/City.
- **Radius Filter:** Option to specify a search radius (e.g., within 5 km).
- **Interruptible:** Built-in "Stop & Save" button to halt scraping anytime and save the data extracted so far.
- **No API Limits:** Completely free to use. No Google Cloud API Keys required.
- **Lightweight Export:** Uses Python's built-in `csv` module, meaning no heavy C++ dependencies like Pandas are needed.

## 🚀 Setup & Installation

**Prerequisites:** Python 3.10+ must be installed on your system


1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/google-maps-extractor.git
   cd google-maps-extractor
   ```

2. **Install Required Packages:**
   ```bash
   python -m pip install -r requirements.txt
   ```

3. **Install Playwright Browsers:**
   ```bash
   python -m playwright install chromium
   ```

## 💻 Usage

Run the graphical interface using:
```bash
python main_ui.py
```

1. Enter your search query (e.g., `Men Saloon`).
2. Enter the Area/Location (e.g., `Chandlodiya, Ahmedabad`).
3. (Optional) Enter a Radius in km (e.g., `5`).
4. Enter the maximum number of results you want.
5. Click **Start Scraping Data**.

The extracted data will be saved inside the `output/` folder as a `.csv` file.

## 📂 Extracted Data Fields
- Name
- Search Category
- Area
- Address
- Phone Number
- Website
- Latitude & Longitude
- Google Maps URL

## ⚠️ Disclaimer
This tool automates a browser to extract publicly available data. Google Maps may occasionally change its HTML structure, which could require minor updates to the script's selectors. Please use responsibly and ensure you comply with Google's Terms of Service regarding automated data extraction.
