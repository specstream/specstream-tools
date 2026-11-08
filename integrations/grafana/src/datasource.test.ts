import { FieldType } from '@grafana/data';
import { listFrame, searchFrame } from './rows';
import { DataSource } from './datasource';

describe('searchFrame', () => {
  it('gives each row its source page and one column per fact', () => {
    const frame = searchFrame('A', {
      rows: [
        { name: 'Acme', page: 'https://acme.example/about', snippet: 's', probability: 0.9, fields: { Founded: { value: '1999', page: 'https://acme.example/about' } } },
      ],
    });
    const names = frame.fields.map((f) => f.name);
    expect(names).toEqual(['Name', 'Founded', 'Match', 'Snippet', 'Source']);
    expect(frame.fields[1].values[0]).toBe('1999');
    expect(frame.fields[4].values[0]).toBe('https://acme.example/about');
    expect(frame.fields[2].type).toBe(FieldType.number);
  });
  it('returns an empty table for no rows', () => {
    expect(searchFrame('A', {}).length).toBe(0);
  });
});

describe('listFrame', () => {
  it('turns cells into columns and keeps the first source', () => {
    const frame = listFrame('B', {
      name: 'Clinics',
      rows: [
        {
          cells: [
            { column_id: 'c1', label: 'Name', display: 'North Clinic', provenance: { source_url: 'https://n.example' } },
            { column_id: 'c2', label: 'Phone', absence: true },
          ],
        },
      ],
    });
    expect(frame.name).toBe('Clinics');
    expect(frame.fields.map((f) => f.name)).toEqual(['Name', 'Phone', 'Source']);
    expect(frame.fields[1].values[0]).toBe('');
    expect(frame.fields[2].values[0]).toBe('https://n.example');
  });
});

describe('DataSource.filterQuery', () => {
  const ds = new DataSource({ url: '/api/ds/proxy/1' } as any);
  it('needs a question in search mode and a list in list mode', () => {
    expect(ds.filterQuery({ refId: 'A', mode: 'search', question: ' ' })).toBe(false);
    expect(ds.filterQuery({ refId: 'A', mode: 'search', question: 'x' })).toBe(true);
    expect(ds.filterQuery({ refId: 'A', mode: 'list' })).toBe(false);
    expect(ds.filterQuery({ refId: 'A', mode: 'list', listId: 'l1' })).toBe(true);
  });
});
