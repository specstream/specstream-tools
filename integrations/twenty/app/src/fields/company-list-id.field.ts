import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { LIST_ID_FIELD_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';

export default defineField({
  universalIdentifier: LIST_ID_FIELD_UNIVERSAL_IDENTIFIER,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  name: 'specstreamListId',
  type: FieldType.TEXT,
  label: 'SpecStream list ID',
  description: 'The SpecStream list that holds this research. Open it at specstream.ai/workspace.',
  icon: 'IconHash',
});
