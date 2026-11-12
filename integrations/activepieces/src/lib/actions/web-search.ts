import { createAction, Property } from '@activepieces/pieces-framework';
import { HttpMethod } from '@activepieces/pieces-common';
import { specstreamAuth } from '../auth';
import { specstreamApi } from '../common/client';

export const webSearchAction = createAction({
  auth: specstreamAuth,
  name: 'web_search',
  displayName: 'Web Search',
  description: 'Answer a question from the live web in seconds with the SpecStream Search API ($5 per 1,000 searches of up to 10 results, or $1 on the fast tier, source URL and read time on every value).',
  props: {
    q: Property.ShortText({
      displayName: 'Search Query',
      description: 'The question or search query in everyday words (1 to 2,000 characters). Quoted phrases are searched as phrases.',
      required: true,
    }),
    passages: Property.Checkbox({
      displayName: 'Include Passages',
      description: 'Include the main text passages of the top matching pages in the response.',
      required: false,
      defaultValue: false,
    }),
  },
  async run(context) {
    const q = String(context.propsValue.q ?? '').trim();
    if (!q || q.length > 2000) {
      throw new Error('Search Query must be between 1 and 2,000 characters.');
    }
    const params = new URLSearchParams({ q });
    if (context.propsValue.passages) {
      params.set('passages', 'true');
    }
    return specstreamApi.call({
      apiKey: context.auth.secret_text,
      method: HttpMethod.GET,
      path: `/v1/web-search?${params.toString()}`,
    });
  },
});
