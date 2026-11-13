import { describe, expect, it } from 'vitest';

import { createSpecStream, SPECSTREAM_API, type RowsPage } from 'src/specstream/api';
import {
  collectResearch,
  startResearch,
  type CompanyResearch,
  type Crm,
} from 'src/specstream/enrich';
import { domainOf, maxCents, requestFor, runKey, type Company } from 'src/specstream/request';
import { researchText } from 'src/specstream/result';
import { createCrm } from 'src/specstream/twenty';

const NOW = new Date('2026-11-12T10:00:00Z');
const ACME: Company = {
  id: '0d1e2f3a-4b5c-4d6e-8f70-112233445566',
  name: 'Acme Robotics',
  domainName: { primaryLinkUrl: 'https://www.acme-robotics.com/about' },
};

type Call = { method: string; path: string; body?: any; authorization: string | null };

// A scripted SpecStream: each "METHOD /path" answers with a status and a body. No network.
const scripted = (answers: Record<string, [number, unknown]>) => {
  const calls: Call[] = [];
  const fetchImpl = (async (url: string | URL | Request, init?: RequestInit) => {
    const address = String(url);
    expect(address.startsWith(`${SPECSTREAM_API}/`)).toBe(true);
    const path = address.slice(SPECSTREAM_API.length).split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({
      method,
      path,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
      authorization: new Headers(init?.headers).get('authorization'),
    });
    const [status, body] = answers[`${method} ${path}`] ?? [404, { error: { message: 'Not found.' } }];
    return new Response(JSON.stringify(body), { status });
  }) as typeof globalThis.fetch;
  return { specstream: createSpecStream('test-key', fetchImpl), calls };
};

const memoryCrm = (companies: Company[]) => {
  const updates: { id: string; fields: CompanyResearch }[] = [];
  const crm: Crm = {
    company: async (id) => companies.find((company) => company.id === id) ?? null,
    update: async (id, fields) => {
      updates.push({ id, fields });
      Object.assign(companies.find((company) => company.id === id) ?? {}, fields);
    },
    running: async () =>
      companies.filter((company) => company.specstreamResearchStatus === 'RUNNING'),
  };
  return { crm, updates };
};

const QUOTE = { quote_id: 'cqt_1', quote_hash: 'hash', maximum_cents: 15 };

describe('the request', () => {
  it('names the company by its name and its website', () => {
    expect(domainOf(ACME)).toBe('acme-robotics.com');
    expect(requestFor(ACME, 'number of employees, LinkedIn page.')).toBe(
      'The company Acme Robotics (website acme-robotics.com). For it: number of employees, LinkedIn page.',
    );
  });

  it('is refused for a record with no name and no website', () => {
    expect(requestFor({ id: ACME.id, name: '  ', domainName: null }, 'employees')).toBeNull();
  });

  it('uses one key per company, request and day', () => {
    const request = requestFor(ACME, 'employees') as string;
    expect(runKey(ACME.id, request, NOW)).toBe(runKey(ACME.id, request, NOW));
    expect(runKey(ACME.id, request, NOW)).toMatch(/^twenty-[0-9a-f]{32}$/);
    expect(runKey(ACME.id, request, new Date('2026-11-13T10:00:00Z'))).not.toBe(
      runKey(ACME.id, request, NOW),
    );
    expect(runKey('another-id', request, NOW)).not.toBe(runKey(ACME.id, request, NOW));
  });

  it('never reads a broken maximum as no limit', () => {
    expect(maxCents('0.50')).toBe(50);
    expect(maxCents(undefined)).toBe(100);
    expect(maxCents('abc')).toBe(100);
    expect(maxCents('-3')).toBe(100);
  });
});

describe('starting the research', () => {
  it('reads, prices and starts the run, then marks the company as running', async () => {
    const { specstream, calls } = scripted({
      'POST /v1/parse': [200, { status: 'runnable', ast_hash: 'ast_1' }],
      'POST /v1/capacity/quotes': [200, QUOTE],
      'POST /v1/capacity/executions': [200, { find_id: 'fnd_1', state: 'running' }],
    });
    const { crm, updates } = memoryCrm([{ ...ACME }]);

    const result = await startResearch({ crm, specstream, settings: {}, now: NOW }, ACME.id);

    expect(result.status).toBe('RUNNING');
    expect(result.listLink).toBe('https://specstream.ai/workspace/collections/fnd_1');
    expect(calls.map((call) => `${call.method} ${call.path}`)).toEqual([
      expect.stringMatching(/^GET \/v1\/capacity\/requests\/twenty-/),
      'POST /v1/parse',
      'POST /v1/capacity/quotes',
      'POST /v1/capacity/executions',
    ]);
    expect(calls.every((call) => call.authorization === 'Bearer test-key')).toBe(true);
    expect(calls[2].body).toEqual({ ast_hash: 'ast_1', operation: 'find', requested_units: 1 });
    expect(calls[3].body).toMatchObject({ quote_id: 'cqt_1', quote_hash: 'hash', confirm_max_cents: 15 });
    expect(calls[3].body.idempotency_key).toMatch(/^twenty-/);
    expect(updates).toEqual([
      {
        id: ACME.id,
        fields: {
          specstreamResearchStatus: 'RUNNING',
          specstreamListId: 'fnd_1',
          specstreamResearchNote: '',
        },
      },
    ]);
  });

  it('buys nothing when the price is above the maximum', async () => {
    const { specstream, calls } = scripted({
      'POST /v1/parse': [200, { status: 'runnable', ast_hash: 'ast_1' }],
      'POST /v1/capacity/quotes': [200, { ...QUOTE, maximum_cents: 100 }],
    });
    const { crm, updates } = memoryCrm([{ ...ACME }]);

    const result = await startResearch(
      { crm, specstream, settings: { maxPriceUsd: '0.50' }, now: NOW },
      ACME.id,
    );

    expect(result.status).toBe('NEEDS_ATTENTION');
    expect(result.message).toContain('$1.00');
    expect(result.message).toContain('$0.50');
    expect(calls.some((call) => call.path === '/v1/capacity/executions')).toBe(false);
    expect(updates[0].fields.specstreamResearchStatus).toBe('NEEDS_ATTENTION');
  });

  it('reaches the run a second click already started instead of buying it again', async () => {
    const request = requestFor(ACME, undefined) as string;
    const key = runKey(ACME.id, request, NOW);
    const { specstream, calls } = scripted({
      [`GET /v1/capacity/requests/${key}`]: [200, { find_id: 'fnd_1', state: 'running' }],
    });
    const { crm } = memoryCrm([{ ...ACME }]);

    const result = await startResearch({ crm, specstream, settings: {}, now: NOW }, ACME.id);

    expect(result).toMatchObject({ status: 'RUNNING', listId: 'fnd_1' });
    expect(calls).toHaveLength(1);
  });

  it('calls nothing for a company with no name and no website', async () => {
    const { specstream, calls } = scripted({});
    const { crm, updates } = memoryCrm([{ id: ACME.id, name: '' }]);

    const result = await startResearch({ crm, specstream, settings: {}, now: NOW }, ACME.id);

    expect(result.status).toBe('NEEDS_ATTENTION');
    expect(calls).toHaveLength(0);
    expect(updates[0].fields.specstreamResearchNote).toContain('name or a website');
  });

  it('writes what SpecStream says when it refuses the key', async () => {
    const { specstream } = scripted({ 'POST /v1/parse': [401, {}] });
    const { crm, updates } = memoryCrm([{ ...ACME }]);

    const result = await startResearch({ crm, specstream, settings: {}, now: NOW }, ACME.id);

    expect(result.status).toBe('NEEDS_ATTENTION');
    expect(updates[0].fields.specstreamResearchNote).toContain('refused the API key');
  });

  it('stops when SpecStream cannot read the request', async () => {
    const { specstream, calls } = scripted({
      'POST /v1/parse': [200, { status: 'needs_clarification', read_back: 'A company' }],
    });
    const { crm } = memoryCrm([{ ...ACME }]);

    const result = await startResearch({ crm, specstream, settings: {}, now: NOW }, ACME.id);

    expect(result.message).toContain('"A company"');
    expect(calls.some((call) => call.path === '/v1/capacity/quotes')).toBe(false);
  });
});

const page = (status: string, withRow = true): RowsPage => ({
  find_id: 'fnd_1',
  status,
  entitlement: 'available',
  rows: withRow
    ? [
        {
          entity_id: 'ent_1',
          cells: [
            { label: 'Employees', display: '120' },
            { label: 'Headquarters', value: 'Lyon, France' },
            { label: 'Founded', display: '' },
          ],
        },
      ]
    : [],
  flat_rows: withRow
    ? [{ Employees_source: 'https://acme-robotics.com/about', source_url: 'https://acme-robotics.com' }]
    : [],
});

describe('collecting the research', () => {
  it('writes each fact with its page', () => {
    expect(researchText(page('completed'), NOW)).toBe(
      [
        'Employees: 120 (https://acme-robotics.com/about)',
        'Headquarters: Lyon, France',
        'Source: https://acme-robotics.com',
        'Checked by SpecStream on 2026-11-12',
      ].join('\n'),
    );
    expect(researchText(page('completed', false), NOW)).toBeNull();
  });

  const running = (): Company => ({
    ...ACME,
    specstreamResearchStatus: 'RUNNING',
    specstreamListId: 'fnd_1',
  });

  it('fills the company when the run ended', async () => {
    const { specstream } = scripted({ 'GET /v1/finds/fnd_1/rows': [200, page('completed')] });
    const { crm, updates } = memoryCrm([running()]);

    const result = await collectResearch({ crm, specstream, now: NOW });

    expect(result).toEqual({ checked: 1, filled: 1, waiting: 0, stopped: 0 });
    expect(updates[0].fields.specstreamResearchStatus).toBe('DONE');
    expect(updates[0].fields.specstreamResearch).toContain('Employees: 120');
  });

  it('leaves a run that is still going', async () => {
    const { specstream } = scripted({ 'GET /v1/finds/fnd_1/rows': [200, page('running', false)] });
    const { crm, updates } = memoryCrm([running()]);

    expect(await collectResearch({ crm, specstream, now: NOW })).toMatchObject({ waiting: 1 });
    expect(updates).toHaveLength(0);
  });

  it('says so when nothing was found, and when the run failed', async () => {
    const empty = scripted({ 'GET /v1/finds/fnd_1/rows': [200, page('completed', false)] });
    const first = memoryCrm([running()]);
    await collectResearch({ crm: first.crm, specstream: empty.specstream, now: NOW });
    expect(first.updates[0].fields.specstreamResearchStatus).toBe('NOT_FOUND');

    const failed = scripted({ 'GET /v1/finds/fnd_1/rows': [200, page('failed', false)] });
    const second = memoryCrm([running()]);
    await collectResearch({ crm: second.crm, specstream: failed.specstream, now: NOW });
    expect(second.updates[0].fields).toMatchObject({
      specstreamResearchStatus: 'NEEDS_ATTENTION',
      specstreamResearchNote: 'The research ended as failed. Run it again.',
    });
  });

  it('waits through an outage and ends the wait on a refusal', async () => {
    const outage = scripted({ 'GET /v1/finds/fnd_1/rows': [503, {}] });
    const first = memoryCrm([running()]);
    expect(
      await collectResearch({ crm: first.crm, specstream: outage.specstream, now: NOW }),
    ).toMatchObject({ waiting: 1, stopped: 0 });
    expect(first.updates).toHaveLength(0);

    const gone = scripted({ 'GET /v1/finds/fnd_1/rows': [410, { error: { message: 'These results aren\'t available.' } }] });
    const second = memoryCrm([running()]);
    await collectResearch({ crm: second.crm, specstream: gone.specstream, now: NOW });
    expect(second.updates[0].fields.specstreamResearchNote).toBe("These results aren't available.");
  });
});

describe('the Twenty records', () => {
  it('reads and writes companies through GraphQL and refuses an ID that is not one', async () => {
    const sent: { query: string; variables?: unknown }[] = [];
    const crm = createCrm(async (body) => {
      sent.push(body);
      return { data: { companies: { edges: [{ node: ACME }] } } };
    });

    expect(await crm.company(ACME.id)).toEqual(ACME);
    await crm.update(ACME.id, { specstreamResearchStatus: 'DONE' });
    expect(await crm.running(500)).toEqual([ACME]);

    expect(sent[0].query).toContain(`id: { eq: "${ACME.id}" }`);
    expect(sent[1].query).toContain(`updateCompany(id: "${ACME.id}", data: $data)`);
    expect(sent[1].variables).toEqual({ data: { specstreamResearchStatus: 'DONE' } });
    expect(sent[2].query).toContain('specstreamResearchStatus: { eq: RUNNING } }, first: 60');
    await expect(crm.company('1") { id } } #')).rejects.toThrow('is not a company ID');
  });

  it('surfaces a GraphQL error', async () => {
    const crm = createCrm(async () => ({ errors: [{ message: 'Forbidden' }] }));
    await expect(crm.running(10)).rejects.toThrow('Forbidden');
  });
});
