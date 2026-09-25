FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Grant permissions to /app and Playwright browser directory
RUN mkdir -p outputs && chmod -R 777 /app /ms-playwright || true

ENV PYTHONUNBUFFERED=1 \
    PORT=7860

EXPOSE 7860

CMD ["python", "app.py"]

