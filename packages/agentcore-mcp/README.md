# SpecStream MCP server for Amazon Bedrock AgentCore

SpecStream, the live web data engine, as an MCP server that Amazon Bedrock AgentCore Runtime hosts.
Agents ask for data in plain words and get structured rows with a source URL for each value.

The container listens on `0.0.0.0:8000/mcp` (stateless Streamable HTTP, as AgentCore Runtime expects)
and answers `GET /ping`. It forwards each MCP message to `https://api.specstream.ai/mcp` with the key
in `SPECSTREAM_API_KEY`. Create a key under Agents & API at https://specstream.ai/workspace.
New accounts get $10 of credit, with no card.

## Deploy on AgentCore Runtime

1. Build the image for arm64 and push it to your Amazon ECR repository:

   ```bash
   docker buildx build --platform linux/arm64 -t <account>.dkr.ecr.us-east-1.amazonaws.com/specstream-mcp:1.0.0 --push .
   ```

2. Create an IAM role that `bedrock-agentcore.amazonaws.com` can assume.

3. Create the agent runtime:

   ```bash
   aws bedrock-agentcore-control create-agent-runtime \
     --region us-east-1 \
     --agent-runtime-name specstream_mcp \
     --agent-runtime-artifact '{"containerConfiguration":{"containerUri":"<account>.dkr.ecr.us-east-1.amazonaws.com/specstream-mcp:1.0.0"}}' \
     --role-arn <role ARN> \
     --network-configuration '{"networkMode":"PUBLIC"}' \
     --protocol-configuration '{"serverProtocol":"MCP"}' \
     --environment-variables '{"SPECSTREAM_API_KEY":"<your SpecStream API key>"}'
   ```

4. Call it with `aws bedrock-agentcore invoke-agent-runtime`, or add the runtime as a target of an
   AgentCore Gateway.

Without a key the server still answers `initialize` and `tools/list`, and each tool call says how to
get a key.
