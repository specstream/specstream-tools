import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { RESEARCH_FIELD_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

export default defineField({
  universalIdentifier: RESEARCH_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  name: 'specstreamResearch',
  type: FieldType.TEXT,
  label: 'Web research',
  description: 'The facts SpecStream found for this company, each with the page it was read from.',
  icon: 'IconWorldSearch',
});
