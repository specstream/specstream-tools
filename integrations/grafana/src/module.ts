import { DataSourcePlugin } from '@grafana/data';
import { DataSource } from './datasource';
import { ConfigEditor } from './components/ConfigEditor';
import { QueryEditor } from './components/QueryEditor';
import { SpecStreamQuery, SpecStreamOptions } from './types';

export const plugin = new DataSourcePlugin<DataSource, SpecStreamQuery, SpecStreamOptions>(DataSource)
  .setConfigEditor(ConfigEditor)
  .setQueryEditor(QueryEditor);
