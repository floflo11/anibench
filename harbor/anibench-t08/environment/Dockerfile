FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy
RUN pip install --no-cache-dir numpy pillow scipy
WORKDIR /app
COPY image.png /app/image.png
COPY vendor/ /app/vendor/
