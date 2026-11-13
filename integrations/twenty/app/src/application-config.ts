import { defineApplication, FieldType } from 'twenty-sdk/define';

import {
  API_KEY_VARIABLE_UNIVERSAL_IDENTIFIER,
  APP_DESCRIPTION,
  APP_DISPLAY_NAME,
  APPLICATION_UNIVERSAL_IDENTIFIER,
  FACTS_VARIABLE_UNIVERSAL_IDENTIFIER,
  MAX_PRICE_VARIABLE_UNIVERSAL_IDENTIFIER,
  NEW_COMPANIES_VARIABLE_UNIVERSAL_IDENTIFIER,
} from 'src/constants/universal-identifiers';
import { DEFAULT_FACTS, DEFAULT_MAX_PRICE_USD } from 'src/specstream/request';

export default defineApplication({
  universalIdentifier: APPLICATION_UNIVERSAL_IDENTIFIER,
  displayName: APP_DISPLAY_NAME,
  description: APP_DESCRIPTION,
  author: 'SpecStream',
  category: 'Enrichment',
  logo: 'public/logo.svg',
  websiteUrl: 'https://specstream.ai',
  termsUrl: 'https://specstream.ai/terms',
  emailSupport: 'support@specstream.ai',
  applicationVariables: {
    SPECSTREAM_API_KEY: {
      universalIdentifier: API_KEY_VARIABLE_UNIVERSAL_IDENTIFIER,
      label: 'SpecStream API key',
      description: 'Create a key at https://specstream.ai/workspace. It is sent only to api.specstream.ai.',
      isSecret: true,
      isRequired: true,
    },
    SPECSTREAM_FACTS: {
      universalIdentifier: FACTS_VARIABLE_UNIVERSAL_IDENTIFIER,
      label: 'Facts to find',
      description: 'What to find for each company, in plain words, separated by commas.',
      value: DEFAULT_FACTS,
    },
    SPECSTREAM_MAX_PRICE_USD: {
      universalIdentifier: MAX_PRICE_VARIABLE_UNIVERSAL_IDENTIFIER,
      label: 'Maximum price per company (USD)',
      description:
        'The research of one company never starts when its quoted maximum is above this amount.',
      type: FieldType.NUMBER,
      value: DEFAULT_MAX_PRICE_USD,
    },
    SPECSTREAM_RESEARCH_NEW_COMPANIES: {
      universalIdentifier: NEW_COMPANIES_VARIABLE_UNIVERSAL_IDENTIFIER,
      label: 'Research every new company',
      description:
        'When on, each company added to the workspace is researched and charged without a click. Off by default.',
      type: FieldType.BOOLEAN,
      value: false,
    },
  },
});
