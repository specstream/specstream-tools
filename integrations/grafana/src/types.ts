import { DataSourceJsonData } from '@grafana/data';
import { DataQuery } from '@grafana/schema';

export type QueryMode = 'search' | 'list';

/** The Search API's speed. 'fast' costs $1 per 1,000 searches; left out, the API's default runs. */
export type SearchSpeed = 'fast' | 'default';

export interface SpecStreamQuery extends DataQuery {
  mode?: QueryMode;
  question?: string;
  speed?: SearchSpeed;
  listId?: string;
}

export const DEFAULT_QUERY: Partial<SpecStreamQuery> = {
  mode: 'search',
};

export interface SpecStreamOptions extends DataSourceJsonData {}

export interface SpecStreamSecureJsonData {
  apiKey?: string;
}

export interface ListSummary {
  id: string;
  name?: string;
}
