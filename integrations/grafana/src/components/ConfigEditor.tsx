import React, { ChangeEvent } from 'react';
import { InlineField, SecretInput } from '@grafana/ui';
import { DataSourcePluginOptionsEditorProps } from '@grafana/data';
import { SpecStreamOptions, SpecStreamSecureJsonData } from '../types';

interface Props extends DataSourcePluginOptionsEditorProps<SpecStreamOptions, SpecStreamSecureJsonData> {}

export function ConfigEditor({ onOptionsChange, options }: Props) {
  const { secureJsonFields, secureJsonData } = options;

  const onAPIKeyChange = (event: ChangeEvent<HTMLInputElement>) => {
    onOptionsChange({ ...options, secureJsonData: { apiKey: event.target.value } });
  };

  const onResetAPIKey = () => {
    onOptionsChange({
      ...options,
      secureJsonFields: { ...options.secureJsonFields, apiKey: false },
      secureJsonData: { ...options.secureJsonData, apiKey: '' },
    });
  };

  return (
    <InlineField label="API key" labelWidth={14} interactive tooltip="Make a key at specstream.ai">
      <SecretInput
        required
        id="config-editor-api-key"
        isConfigured={!!secureJsonFields?.apiKey}
        value={secureJsonData?.apiKey}
        placeholder="Paste your SpecStream API key"
        width={40}
        onReset={onResetAPIKey}
        onChange={onAPIKeyChange}
      />
    </InlineField>
  );
}
