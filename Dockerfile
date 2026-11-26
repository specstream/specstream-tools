# Runs the SpecStream MCP server over stdio for clients and directories that start containers.
# Without SPECSTREAM_API_KEY it lists its tools; with one it runs them on your account.
FROM python:3.12-slim
RUN pip install --no-cache-dir specstream-mcp-stdio==1.2.6
ENV SPECSTREAM_MCP_URL=https://api.specstream.ai/mcp
ENTRYPOINT ["specstream-mcp-stdio"]
