# SpecStream browser runner: ws://<container>:3000 starts a hosted Chromium for each CDP connection.
# The browser runs at SpecStream, so the image holds no Chromium and needs no extra memory or shm.
FROM python:3.12-slim
LABEL org.opencontainers.image.title="SpecStream browser runner" \
      org.opencontainers.image.description="A CDP address for Puppeteer and Playwright that starts a hosted browser for each connection" \
      org.opencontainers.image.source="https://github.com/specstream/specstream-tools" \
      org.opencontainers.image.url="https://specstream.ai"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system runner
COPY runner.py .
USER runner
ENV PYTHONUNBUFFERED=1 PORT=3000
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s CMD ["python", "-c", "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','3000'), timeout=4)"]
CMD ["python", "runner.py"]
