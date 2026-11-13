import { getBackendSrv } from '@grafana/runtime';
import { CoreApp, DataQueryRequest, DataQueryResponse, DataSourceApi, DataSourceInstanceSettings } from '@grafana/data';
import { lastValueFrom } from 'rxjs';

import { DEFAULT_QUERY, ListSummary, SpecStreamOptions, SpecStreamQuery } from './types';
import { listFrame, searchFrame } from './rows';

export class DataSource extends DataSourceApi<SpecStreamQuery, SpecStreamOptions> {
  baseUrl: string;

  constructor(instanceSettings: DataSourceInstanceSettings<SpecStreamOptions>) {
    super(instanceSettings);
    this.baseUrl = `${instanceSettings.url}/specstream`;
  }

  getDefaultQuery(_: CoreApp): Partial<SpecStreamQuery> {
    return DEFAULT_QUERY;
  }

  filterQuery(query: SpecStreamQuery): boolean {
    return query.mode === 'list' ? !!query.listId : !!query.question?.trim();
  }

  private async get(path: string, params?: Record<string, string | number>): Promise<any> {
    const response = await lastValueFrom(
      getBackendSrv().fetch({ url: `${this.baseUrl}${path}`, method: 'GET', params })
    );
    return response.data;
  }

  async getLists(): Promise<ListSummary[]> {
    const page = await this.get('/v1/workspace/collections', { limit: 100, sort: 'recent' });
    return (page?.collections ?? []).map((c: any) => ({ id: String(c.id), name: c.name }));
  }

  async query(options: DataQueryRequest<SpecStreamQuery>): Promise<DataQueryResponse> {
    const data = await Promise.all(
      options.targets
        .filter((t) => this.filterQuery(t))
        .map(async (target) => {
          if (target.mode === 'list') {
            const detail = await this.get(`/v1/workspace/collections/${encodeURIComponent(target.listId!)}`);
            return listFrame(target.refId, detail);
          }
          const params: Record<string, string> = { q: target.question!.trim() };
          if (target.speed) {
            params.speed = target.speed;
          }
          const reply = await this.get('/v1/web-search', params);
          return searchFrame(target.refId, reply);
        })
    );
    return { data };
  }

  async testDatasource() {
    try {
      await this.get('/v1/workspace/collections', { limit: 1 });
      return { status: 'success', message: 'Connected to SpecStream.' };
    } catch (error: any) {
      const status = error?.status ?? error?.data?.status;
      return {
        status: 'error',
        message:
          status === 401 || status === 403
            ? 'SpecStream rejected the API key. Make one at specstream.ai and paste it again.'
            : `Could not reach SpecStream${status ? ` (HTTP ${status})` : ''}.`,
      };
    }
  }
}
