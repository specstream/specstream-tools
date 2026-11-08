import { DataSourceJsonData } from '@grafana/data';
import { DataQuery } from '@grafana/schema';

export type QueryMode = 'search' | 'list';

export interface SpecStreamQuery extends DataQuery {
  mode?: QueryMode;
  question?: string;
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
