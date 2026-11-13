import { defineLogicFunction } from 'twenty-sdk/define';
import { jsonSchemaToInputSchema, type InputJsonSchema } from 'twenty-sdk/logic-function';

import { RESEARCH_COMPANY_FUNCTION_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';
import { startResearch, type StartResult } from 'src/specstream/enrich';
import { MISSING_KEY, settingsFromEnv, specstreamFromEnv } from 'src/specstream/runtime';
import { twentyCrm } from 'src/specstream/twenty';

const inputSchema: InputJsonSchema = {
  type: 'object',
  properties: {
    companyId: {
      type: 'string',
      label: 'Company ID',
      description: 'The ID of the company record to research.',
    },
  },
  required: ['companyId'],
};

const handler = async (params: { companyId: string }): Promise<StartResult> => {
  const specstream = specstreamFromEnv();
  if (!specstream) return { status: 'NEEDS_ATTENTION', message: MISSING_KEY };
  return startResearch(
    { crm: twentyCrm(), specstream, settings: settingsFromEnv() },
    String(params.companyId ?? '').trim(),
  );
};

export default defineLogicFunction({
  universalIdentifier: RESEARCH_COMPANY_FUNCTION_UNIVERSAL_IDENTIFIER,
  name: 'research-company',
  description:
    'Research one company on the live web with SpecStream. Starts the research and returns at once; the company record is filled in a few minutes later. Each run is charged to the SpecStream account.',
  timeoutSeconds: 60,
  handler,
  toolTriggerSettings: { inputSchema },
  workflowActionTriggerSettings: {
    label: 'Research company with SpecStream',
    icon: 'IconWorldSearch',
    inputSchema: jsonSchemaToInputSchema(inputSchema),
  },
});
