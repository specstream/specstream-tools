import { MetadataApiClient } from 'twenty-client-sdk/metadata';
import { RestApiClient } from 'twenty-client-sdk/rest';
import { APPLICATION_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';
import { createCrm } from 'src/specstream/twenty';
import { describe, expect, it } from 'vitest';

// Needs a disposable Twenty workspace (TWENTY_API_URL, TWENTY_API_KEY). Never calls SpecStream.
describe('App installation', () => {
  it('should find the installed app in the applications list', async () => {
    const client = new MetadataApiClient();

    const result = await client.query({
      findManyApplications: {
        id: true,
        name: true,
        universalIdentifier: true,
      },
    });

    const app = result.findManyApplications.find(
      (a: { universalIdentifier: string }) =>
        a.universalIdentifier === APPLICATION_UNIVERSAL_IDENTIFIER,
    );

    expect(app).toBeDefined();
  });
});

describe('The research fields on Company', () => {
  it('should write a status and find the company among the running ones', async () => {
    const client = new RestApiClient();
    const post = (body: unknown) => client.post('/graphql', body);
    const crm = createCrm(post);

    const created = (await post({
      query: 'mutation { createCompany(data: { name: "SpecStream integration test" }) { id } }',
    })) as { data: { createCompany: { id: string } } };
    const id = created.data.createCompany.id;

    try {
      await crm.update(id, { specstreamResearchStatus: 'RUNNING', specstreamListId: 'fnd_test' });
      const running = await crm.running(60);
      expect(running.some((company) => company.id === id)).toBe(true);
      expect((await crm.company(id))?.specstreamListId).toBe('fnd_test');
    } finally {
      await post({ query: `mutation { destroyCompany(id: "${id}") { id } }` });
    }
  });
});
