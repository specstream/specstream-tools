import { createHash } from 'node:crypto';

export const DEFAULT_FACTS =
  'what the company does, number of employees, headquarters city, year founded, LinkedIn page';
export const DEFAULT_MAX_PRICE_USD = 1;

export type Company = {
  id: string;
  name?: string | null;
  domainName?: { primaryLinkUrl?: string | null } | string | null;
  specstreamResearchStatus?: string | null;
  specstreamListId?: string | null;
};

// "https://www.acme.com/about" -> "acme.com". Empty when the record has no website.
export const domainOf = (company: Company): string => {
  const raw =
    typeof company.domainName === 'string'
      ? company.domainName
      : (company.domainName?.primaryLinkUrl ?? '');
  const text = String(raw ?? '').trim();
  if (!text) return '';
  try {
    const host = new URL(/^[a-z]+:\/\//i.test(text) ? text : `https://${text}`).hostname;
    return host.replace(/^www\./i, '').toLowerCase();
  } catch {
    return '';
  }
};

const clean = (text: string): string => text.replace(/\s+/g, ' ').trim();

// The request in plain words, or null when the record has neither a name nor a website:
// a search for an unnamed company would be charged and could return some other company.
export const requestFor = (company: Company, facts: string | undefined): string | null => {
  const name = clean(String(company.name ?? ''));
  const domain = domainOf(company);
  if (!name && !domain) return null;
  const who = name && domain ? `${name} (website ${domain})` : name || `with the website ${domain}`;
  const wanted = clean(String(facts ?? '')).replace(/\.+$/, '') || DEFAULT_FACTS;
  return `The company ${who}. For it: ${wanted}.`;
};

// One key per company, request and UTC day: a second click, a retry after a lost answer or a
// workflow that fires twice reaches the run that already started instead of buying it again.
export const runKey = (companyId: string, request: string, now: Date = new Date()): string => {
  const day = now.toISOString().slice(0, 10);
  const digest = createHash('sha256').update(`${companyId}|${request}|${day}`).digest('hex');
  return `twenty-${digest.slice(0, 32)}`;
};

// The most one company may cost, in cents. A missing or unreadable setting is the default, never "no limit".
export const maxCents = (setting: string | undefined): number => {
  const usd = Number(String(setting ?? '').trim() || DEFAULT_MAX_PRICE_USD);
  if (!Number.isFinite(usd) || usd <= 0) return Math.round(DEFAULT_MAX_PRICE_USD * 100);
  return Math.round(usd * 100);
};
