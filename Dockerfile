FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# Create user 1000 required by Hugging Face Spaces
RUN useradd -m -u 1000 user

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Grant permissions to /app and Playwright browser directory
RUN mkdir -p outputs && chmod -R 777 /app /ms-playwright || true

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PORT=7860

EXPOSE 7860

CMD ["python", "app.py"]

