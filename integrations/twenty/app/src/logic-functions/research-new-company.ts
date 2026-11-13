import { defineLogicFunction, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';
import type { DatabaseEventPayload, ObjectRecordCreateEvent } from 'twenty-sdk/logic-function';

import { NEW_COMPANY_FUNCTION_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';
import { startResearch } from 'src/specstream/enrich';
import { settingsFromEnv, specstreamFromEnv } from 'src/specstream/runtime';
import { twentyCrm } from 'src/specstream/twenty';

type CompanyCreated = DatabaseEventPayload<ObjectRecordCreateEvent<{ id: string }>>;

// Runs only when the workspace turned "Research every new company" on: a new record is never
// charged for without that choice.
const handler = async (event: CompanyCreated) => {
  if (process.env.SPECSTREAM_RESEARCH_NEW_COMPANIES !== 'true') return { skipped: 'off' };
  const specstream = specstreamFromEnv();
  if (!specstream) return { skipped: 'no API key' };
  return startResearch(
    { crm: twentyCrm(), specstream, settings: settingsFromEnv() },
    event.recordId,
  );
};

export default defineLogicFunction({
  universalIdentifier: NEW_COMPANY_FUNCTION_UNIVERSAL_IDENTIFIER,
  name: 'research-new-company',
  description: 'Researches each new company when the workspace turned that setting on.',
  timeoutSeconds: 60,
  handler,
  eventTriggerSettings: {
    on: 'recordEvent',
    objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
    action: 'created',
  },
});
