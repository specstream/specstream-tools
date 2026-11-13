import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { RESEARCH_STATUS_FIELD_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

// The values are the ResearchStatus of src/specstream/enrich.ts.
export default defineField({
  universalIdentifier: RESEARCH_STATUS_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  name: 'specstreamResearchStatus',
  type: FieldType.SELECT,
  label: 'Web research status',
  description: 'Where the SpecStream research of this company stands.',
  icon: 'IconProgressCheck',
  options: [
    { value: 'RUNNING', label: 'Running', position: 0, color: 'blue' },
    { value: 'DONE', label: 'Done', position: 1, color: 'green' },
    { value: 'NOT_FOUND', label: 'Nothing found', position: 2, color: 'gray' },
    { value: 'NEEDS_ATTENTION', label: 'Needs attention', position: 3, color: 'orange' },
  ],
});
