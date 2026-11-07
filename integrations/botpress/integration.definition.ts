import { IntegrationDefinition, z } from '@botpress/sdk'
import { integrationName } from './package.json'

const cell = z.object({
  field: z.string().title('Field').describe('The column, such as "Business" or "Website"'),
  value: z.string().title('Value').describe('The value as shown, empty when the web had no value'),
  sourceUrl: z.string().optional().title('Source').describe('The page the value came from'),
})

export default new IntegrationDefinition({
  name: integrationName,
  title: 'SpecStream',
  description:
    'The live web data engine. Search API: the most accurate web search API in the world, $5 per 1,000 searches (specstream.ai/benchmarks). Extract API: $0.80 per 1,000 pages. Deep Search: structured rows.',
  version: '1.0.1',
  readme: 'hub.md',
  icon: 'icon.svg',
  configuration: {
    schema: z.object({
      apiKey: z
        .string()
        .secret()
        .min(1)
        .title('API key')
        .describe('A SpecStream API key (starts with ss_live_), from Agents & API at specstream.ai'),
      maxPriceUsd: z
        .number()
        .min(0)
        .default(5)
        .title('Most one list may cost (USD)')
        .describe('Approve and run refuses any price above this. Default $5'),
    }),
  },
  actions: {
    getPrice: {
      title: 'Get a price',
      description:
        'Reads a request in plain words and prices it. Nothing runs and nothing is charged. Show the price to the user before Approve and run.',
      input: {
        schema: z.object({
          request: z
            .string()
            .min(1)
            .title('Request')
            .describe('What to find: the things, the place, what every result must meet and the facts to bring back'),
          rows: z.number().min(1).max(10000).default(25).title('Rows').describe('How many results to price'),
        }),
      },
      output: {
        schema: z.object({
          reading: z.string().title('Reading').describe('How SpecStream read the request'),
          quoteId: z.string().title('Quote ID').describe('Pass to Approve and run'),
          quoteHash: z.string().title('Quote hash').describe('Pass to Approve and run'),
          maximumCents: z.number().title('Most it can cost (cents)').describe('The most this run can cost, in cents. Pass as approvedCents once the user agrees'),
          price: z.string().title('Price').describe('The most it can cost, such as "$2.50"'),
          expiresAt: z.string().title('Expires at').describe('When this price stops being valid'),
        }),
      },
    },
    approveAndRun: {
      title: 'Approve and run',
      description:
        "Starts the run for a price the user approved. Call it only after the user says yes to that price. Never costs more than the approved price, and approving the same quote twice doesn't charge twice.",
      input: {
        schema: z.object({
          quoteId: z.string().min(1).title('Quote ID').describe('From Get a price'),
          quoteHash: z.string().min(1).title('Quote hash').describe('From Get a price'),
          approvedCents: z
            .number()
            .min(0)
            .title('Approved price (cents)')
            .describe('The price the user approved: maximumCents from Get a price'),
        }),
      },
      output: {
        schema: z.object({
          findId: z.string().title('Find ID').describe('The run, for Get rows'),
          state: z.string().title('State').describe('running once the run has started'),
        }),
      },
    },
    getRows: {
      title: 'Get rows',
      description:
        'Reads the results of a run, with the source URL and read time on every value. Free. Call again with nextCursor for more, or later while the run is still going.',
      input: {
        schema: z.object({
          findId: z.string().min(1).title('Find ID').describe('From Approve and run'),
          limit: z.number().min(1).max(100).default(25).title('Rows per read').describe('How many rows to read at once, up to 100'),
          cursor: z.string().optional().title('Cursor').describe('nextCursor from the previous read'),
        }),
      },
      output: {
        schema: z.object({
          status: z.string().title('Status').describe('running or completed'),
          acceptedCount: z.number().title('Results so far').describe('How many results the run has found so far'),
          rows: z.array(z.object({ id: z.string(), cells: z.array(cell) })).title('Rows').describe('The results, each with its cells and their sources'),
          nextCursor: z.string().optional().title('Next cursor').describe('Pass as cursor to read the next rows; empty when there are no more'),
        }),
      },
    },
  },
})
