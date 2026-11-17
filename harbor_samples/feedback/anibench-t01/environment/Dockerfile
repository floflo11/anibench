FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy
RUN pip install --no-cache-dir numpy pillow scipy
WORKDIR /app
COPY image.png /app/image.png
COPY vendor/ /app/vendor/
COPY anibench/ /opt/anibench/
RUN chmod 755 /opt/anibench/anibench-preview && ln -sf /opt/anibench/anibench-preview /usr/local/bin/anibench-preview \
 && mkdir -p /var/lib/anibench && chmod 777 /var/lib/anibench
