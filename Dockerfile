FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

WORKDIR /app

COPY requirements.txt requirements.txt

# Install dependencies including Waitress for production
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir flask waitress

COPY . .

# Expose the port
EXPOSE 5000

# Start the Flask app using waitress for production
CMD ["waitress-serve", "--port=5000", "app:app"]
