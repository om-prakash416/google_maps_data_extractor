FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

WORKDIR /app

COPY requirements.txt requirements.txt

# Install dependencies including Waitress for production
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir flask waitress

COPY . .

# Hugging Face Spaces runs as user 1000 by default. Give permissions to write outputs.
RUN mkdir -p outputs && chmod -R 777 /app

# Expose the port required by Hugging Face Spaces
EXPOSE 7860

# Start the Flask app
CMD ["python", "app.py"]
