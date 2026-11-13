# SpecStream deep research for Railway. The standard library only: nothing to install.
FROM python:3.12-slim
WORKDIR /app
COPY app.py .
RUN useradd --system research
USER research
ENV PYTHONUNBUFFERED=1
CMD ["python", "app.py"]
