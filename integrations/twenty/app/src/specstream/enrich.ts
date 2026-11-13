import { SpecStreamError, type SpecStream } from './api';
import { maxCents, requestFor, runKey, type Company } from './request';
import { researchText } from './result';

export type ResearchStatus = 'RUNNING' | 'DONE' | 'NOT_FOUND' | 'NEEDS_ATTENTION';

export type CompanyResearch = {
  specstreamResearchStatus?: ResearchStatus;
  specstreamResearch?: string;
  specstreamResearchNote?: string;
  specstreamListId?: string;
};

// What the app needs from the CRM. The Twenty implementation is in twenty.ts.
export type Crm = {
  company: (id: string) => Promise<Company | null>;
  update: (id: string, fields: CompanyResearch) => Promise<void>;
  running: (limit: number) => Promise<Company[]>;
};

export type Settings = { facts?: string; maxPriceUsd?: string };

export type StartResult = {
  status: ResearchStatus;
  message: string;
  listId?: string;
  listLink?: string;
};

const listLink = (listId: string) => `https://specstream.ai/workspace/collections/${listId}`;
const usd = (cents: number) => `$${(cents / 100).toFixed(2)}`;

// Starts the research for one company. Nothing is bought when the record cannot be named, when
// SpecStream cannot read the request or when the price is above the workspace's maximum.
export const startResearch = async (
  deps: { crm: Crm; specstream: SpecStream; settings: Settings; now?: Date },
  companyId: string,
): Promise<StartResult> => {
  const { crm, specstream, settings } = deps;
  const company = await crm.company(companyId);
  if (!company) {
    return { status: 'NEEDS_ATTENTION', message: `No company has the ID ${companyId}.` };
  }

  const stop = async (message: string): Promise<StartResult> => {
    await crm.update(company.id, {
      specstreamResearchStatus: 'NEEDS_ATTENTION',
      specstreamResearchNote: message,
    });
    return { status: 'NEEDS_ATTENTION', message };
  };
  const started = async (listId: string): Promise<StartResult> => {
    await crm.update(company.id, {
      specstreamResearchStatus: 'RUNNING',
      specstreamListId: listId,
      specstreamResearchNote: '',
    });
    return {
      status: 'RUNNING',
      message: 'The research started. The company record is filled in when it ends.',
      listId,
      listLink: listLink(listId),
    };
  };

  const request = requestFor(company, settings.facts);
  if (!request) return stop('Add a name or a website to the company, then run the research again.');

  try {
    const key = runKey(company.id, request, deps.now);
    const earlier = await specstream.started(key);
    if (earlier?.find_id) return await started(String(earlier.find_id));

    const reading = await specstream.read(request);
    if (reading.status !== 'runnable' || !reading.ast_hash) {
      const read = reading.read_back || reading.canonical_sentence || request;
      return await stop(`SpecStream needs a clearer request. It read: "${read}".`);
    }
    const quote = await specstream.quote(reading.ast_hash);
    const limit = maxCents(settings.maxPriceUsd);
    const price = Number(quote.maximum_cents);
    if (!(price <= limit)) {
      return await stop(
        `This research can cost up to ${usd(price)}, above the maximum of ${usd(limit)} set in the app settings. Nothing was bought.`,
      );
    }
    const run = await specstream.run(quote, key);
    if (!run.find_id) return await stop('SpecStream did not start the research. Run it again.');
    return await started(String(run.find_id));
  } catch (error) {
    if (error instanceof SpecStreamError) return stop(error.message);
    throw error;
  }
};

const WAITING = new Set(['queued', 'planning', 'running']);
const DELIVERED = new Set(['completed', 'partial']);

export type CollectResult = { checked: number; filled: number; waiting: number; stopped: number };

// Reads the lists of the companies whose research is running and writes each ended one to its record.
export const collectResearch = async (
  deps: { crm: Crm; specstream: SpecStream; now?: Date },
  limit = 25,
): Promise<CollectResult> => {
  const { crm, specstream } = deps;
  const result: CollectResult = { checked: 0, filled: 0, waiting: 0, stopped: 0 };
  for (const company of await crm.running(limit)) {
    result.checked++;
    const listId = String(company.specstreamListId ?? '').trim();
    if (!listId) {
      await crm.update(company.id, {
        specstreamResearchStatus: 'NEEDS_ATTENTION',
        specstreamResearchNote: 'The research has no list. Run it again.',
      });
      result.stopped++;
      continue;
    }
    try {
      const page = await specstream.rows(listId);
      if (WAITING.has(page.status)) {
        result.waiting++;
        continue;
      }
      const text = DELIVERED.has(page.status) ? researchText(page, deps.now) : null;
      if (text) {
        await crm.update(company.id, {
          specstreamResearchStatus: 'DONE',
          specstreamResearch: text,
          specstreamResearchNote: '',
        });
        result.filled++;
      } else if (DELIVERED.has(page.status)) {
        await crm.update(company.id, {
          specstreamResearchStatus: 'NOT_FOUND',
          specstreamResearchNote: 'SpecStream found no page that confirms these facts for this company.',
        });
        result.stopped++;
      } else {
        await crm.update(company.id, {
          specstreamResearchStatus: 'NEEDS_ATTENTION',
          specstreamResearchNote: `The research ended as ${page.status}. Run it again.`,
        });
        result.stopped++;
      }
    } catch (error) {
      // A refusal that will not clear by itself ends the wait; an outage or a rate limit is read again next round.
      const final =
        error instanceof SpecStreamError &&
        error.status >= 400 &&
        error.status < 500 &&
        error.status !== 429 &&
        error.status !== 408;
      if (!final) {
        result.waiting++;
        continue;
      }
      await crm.update(company.id, {
        specstreamResearchStatus: 'NEEDS_ATTENTION',
        specstreamResearchNote: (error as Error).message,
      });
      result.stopped++;
    }
  }
  return result;
};
