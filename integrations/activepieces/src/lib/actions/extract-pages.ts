import { createAction, Property } from '@activepieces/pieces-framework';
import { HttpMethod } from '@activepieces/pieces-common';
import { specstreamAuth } from '../auth';
import { specstreamApi } from '../common/client';

export const extractPagesAction = createAction({
  auth: specstreamAuth,
  name: 'extract_pages',
  displayName: 'Extract Pages',
  description: 'Read the main text, title and published date of 1 to 20 web pages, PDFs, Word or Excel files live ($0.80 per 1,000 pages, empty pages free).',
  props: {
    urls: Property.LongText({
      displayName: 'URLs',
      description: '1 to 20 http or https URLs separated by newlines or commas.',
      required: true,
    }),
    format: Property.StaticDropdown({
      displayName: 'Output Format',
      description: 'Markdown (keeps headings, lists and links) or plain text.',
      required: false,
      defaultValue: 'markdown',
      options: {
        options: [
          { label: 'Markdown', value: 'markdown' },
          { label: 'Plain Text', value: 'text' },
        ],
      },
    }),
  },
  async run(context) {
    const urls = String(context.propsValue.urls ?? '')
      .split(/[\r\n,]+/)
      .map((u) => u.trim())
      .filter(Boolean);
    if (urls.length < 1 || urls.length > 20) {
      throw new Error('Provide 1 to 20 http or https URLs.');
    }
    const format = context.propsValue.format === 'text' ? 'text' : 'markdown';
    return specstreamApi.call({
      apiKey: context.auth.secret_text,
      method: HttpMethod.POST,
      path: '/v1/extract',
      body: { urls, format },
    });
  },
});
