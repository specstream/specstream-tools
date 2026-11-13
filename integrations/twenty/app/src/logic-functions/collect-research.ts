import { defineLogicFunction } from 'twenty-sdk/define';

import { COLLECT_RESEARCH_FUNCTION_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';
import { collectResearch, type CollectResult } from 'src/specstream/enrich';
import { specstreamFromEnv } from 'src/specstream/runtime';
import { twentyCrm } from 'src/specstream/twenty';

// Every five minutes: write the research that ended to its company. A workspace with nothing
// running costs one small query and no SpecStream call.
const handler = async (): Promise<CollectResult> => {
  const specstream = specstreamFromEnv();
  if (!specstream) return { checked: 0, filled: 0, waiting: 0, stopped: 0 };
  return collectResearch({ crm: twentyCrm(), specstream });
};

export default defineLogicFunction({
  universalIdentifier: COLLECT_RESEARCH_FUNCTION_UNIVERSAL_IDENTIFIER,
  name: 'collect-research',
  description: 'Writes finished SpecStream research to its company record.',
  timeoutSeconds: 120,
  handler,
  cronTriggerSettings: { pattern: '*/5 * * * *' },
});
