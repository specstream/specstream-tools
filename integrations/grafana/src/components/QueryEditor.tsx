import React, { useEffect, useState } from 'react';
import { InlineField, Input, RadioButtonGroup, Select } from '@grafana/ui';
import { QueryEditorProps, SelectableValue } from '@grafana/data';
import { DataSource } from '../datasource';
import { QueryMode, SearchSpeed, SpecStreamOptions, SpecStreamQuery } from '../types';

type Props = QueryEditorProps<DataSource, SpecStreamQuery, SpecStreamOptions>;

const MODES: Array<SelectableValue<QueryMode>> = [
  { label: 'Search', value: 'search' },
  { label: 'Saved list', value: 'list' },
];

const SPEEDS: Array<SelectableValue<SearchSpeed>> = [
  { label: 'Default', value: 'default', description: 'The answer read from the pages, $5 per 1,000 searches' },
  { label: 'Fast', value: 'fast', description: 'Ranked results in about a second, $1 per 1,000 searches' },
];

export function QueryEditor({ query, onChange, onRunQuery, datasource }: Props) {
  const [lists, setLists] = useState<Array<SelectableValue<string>>>([]);
  const mode = query.mode ?? 'search';

  useEffect(() => {
    if (mode !== 'list') {
      return;
    }
    datasource
      .getLists()
      .then((found) => setLists(found.map((l) => ({ label: l.name || l.id, value: l.id }))))
      .catch(() => setLists([]));
  }, [mode, datasource]);

  return (
    <>
      <InlineField label="Source" labelWidth={14}>
        <RadioButtonGroup
          options={MODES}
          value={mode}
          onChange={(value) => {
            onChange({ ...query, mode: value });
            onRunQuery();
          }}
        />
      </InlineField>
      {mode === 'search' ? (
        <>
          <InlineField
            label="Speed"
            labelWidth={14}
            tooltip="Fast returns ranked results in about a second and costs $1 per 1,000 searches. Default reads the answer from the pages at $5 per 1,000."
          >
            <RadioButtonGroup
              options={SPEEDS}
              value={query.speed ?? 'default'}
              onChange={(value) => {
                onChange({ ...query, speed: value === 'fast' ? 'fast' : undefined });
                onRunQuery();
              }}
            />
          </InlineField>
          <InlineField label="Question" labelWidth={14} grow tooltip="In everyday words, up to 2,000 characters">
            <Input
              id="query-editor-question"
              value={query.question ?? ''}
              placeholder="Which hospitals in Texas opened a new cardiology wing this year?"
              onChange={(e) => onChange({ ...query, question: e.currentTarget.value })}
              onBlur={onRunQuery}
            />
          </InlineField>
        </>
      ) : (
        <InlineField label="List" labelWidth={14}>
          <Select
            inputId="query-editor-list"
            width={40}
            options={lists}
            value={query.listId}
            placeholder="Pick a saved list"
            onChange={(v) => {
              onChange({ ...query, listId: v.value });
              onRunQuery();
            }}
          />
        </InlineField>
      )}
    </>
  );
}
