import { createSpecStream, type SpecStream } from './api';
import type { Settings } from './enrich';

export const MISSING_KEY = 'Add your SpecStream API key in the app settings, then run the research again.';

// The workspace's settings, as Twenty injects them into a logic function run.
export const specstreamFromEnv = (env: NodeJS.ProcessEnv = process.env): SpecStream | null => {
  const key = String(env.SPECSTREAM_API_KEY ?? '').trim();
  return key ? createSpecStream(key) : null;
};

export const settingsFromEnv = (env: NodeJS.ProcessEnv = process.env): Settings => ({
  facts: env.SPECSTREAM_FACTS,
  maxPriceUsd: env.SPECSTREAM_MAX_PRICE_USD,
});
