# SpecStream MCP server for Amazon Bedrock AgentCore Runtime.
# AgentCore runs linux/arm64 images: docker buildx build --platform linux/arm64 -t specstream-mcp .
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY specstream_agentcore_mcp ./specstream_agentcore_mcp
RUN pip install --no-cache-dir . && useradd --uid 1000 --create-home app
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ping', timeout=3)"
CMD ["specstream-agentcore-mcp"]
