import { RestApiClient } from 'twenty-client-sdk/rest';

import type { CompanyResearch, Crm } from './enrich';
import type { Company } from './request';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const FIELDS = 'id name domainName { primaryLinkUrl } specstreamResearchStatus specstreamListId';

type GraphQlAnswer<T> = { data?: T; errors?: { message?: string }[] };
export type GraphQlPost = (body: { query: string; variables?: unknown }) => Promise<unknown>;

// The company records, through the workspace's GraphQL API. Only the four fields this app adds are written.
export const createCrm = (post: GraphQlPost): Crm => {
  const send = async <T>(query: string, variables?: unknown): Promise<T> => {
    const answer = (await post({ query, variables })) as GraphQlAnswer<T>;
    if (answer?.errors?.length) {
      throw new Error(answer.errors[0]?.message || 'Twenty refused the request.');
    }
    return answer?.data as T;
  };
  const checked = (id: string): string => {
    if (!UUID.test(id)) throw new Error(`"${id}" is not a company ID.`);
    return id;
  };

  return {
    company: async (id) => {
      const data = await send<{ companies?: { edges?: { node: Company }[] } }>(
        `query { companies(filter: { id: { eq: "${checked(id)}" } }, first: 1) { edges { node { ${FIELDS} } } } }`,
      );
      return data?.companies?.edges?.[0]?.node ?? null;
    },
    update: async (id, fields: CompanyResearch) => {
      await send(
        `mutation ($data: CompanyUpdateInput!) { updateCompany(id: "${checked(id)}", data: $data) { id } }`,
        { data: fields },
      );
    },
    running: async (limit) => {
      const first = Math.max(1, Math.min(60, Math.floor(limit)));
      const data = await send<{ companies?: { edges?: { node: Company }[] } }>(
        `query { companies(filter: { specstreamResearchStatus: { eq: RUNNING } }, first: ${first}) { edges { node { ${FIELDS} } } } }`,
      );
      return (data?.companies?.edges ?? []).map((edge) => edge.node);
    },
  };
};

// The client acts as the person who started the run, within the app's role; a scheduled run acts as the app.
export const twentyCrm = (): Crm => {
  const client = new RestApiClient();
  return createCrm((body) => client.post('/graphql', body));
};
