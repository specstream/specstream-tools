import { searchFrame } from './rows';
import { DataSource } from './datasource';

const fetch = jest.fn();
jest.mock('@grafana/runtime', () => ({ getBackendSrv: () => ({ fetch }) }));
jest.mock('rxjs', () => ({ lastValueFrom: (v: any) => v }));

describe('search speed', () => {
  const ds = new DataSource({ url: '/api/ds/proxy/1' } as any);
  const ask = async (speed?: 'fast' | 'default') => {
    fetch.mockReset();
    fetch.mockReturnValue(
      Promise.resolve({ data: { data: { rows: [], sources: [{ url: 'https://a.example', title: 'A' }] } } })
    );
    await ds.query({ targets: [{ refId: 'A', mode: 'search', question: 'q', speed }] } as any);
    return fetch.mock.calls[0][0].params;
  };

  it('sends speed=fast when Fast is chosen', async () => {
    expect(await ask('fast')).toEqual({ q: 'q', speed: 'fast' });
  });
  it('sends no speed otherwise, so the API default runs', async () => {
    expect(await ask()).toEqual({ q: 'q' });
  });
  it("lists a fast search's ranked results from the reply's data", () => {
    const frame = searchFrame('A', {
      data: { rows: [], sources: [{ url: 'https://a.example', title: 'A', snippet: 's' }] },
    });
    expect(frame.fields.map((f) => f.name)).toEqual(['Name', 'Match', 'Snippet', 'Source']);
    expect(frame.fields[0].values[0]).toBe('A');
    expect(frame.fields[3].values[0]).toBe('https://a.example');
  });
});
