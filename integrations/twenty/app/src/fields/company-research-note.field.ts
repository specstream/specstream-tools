import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { RESEARCH_NOTE_FIELD_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

export default defineField({
  universalIdentifier: RESEARCH_NOTE_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  name: 'specstreamResearchNote',
  type: FieldType.TEXT,
  label: 'Web research note',
  description: 'Why the research found nothing or needs attention, and what to do about it.',
  icon: 'IconInfoCircle',
});
