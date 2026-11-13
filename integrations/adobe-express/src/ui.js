// The panel. It calls SpecStream with the user's own key, shows the rows, and hands the chosen text to
// code.js (the document sandbox), which puts it on the page.
import addOnUISdk from 'https://express.adobe.com/static/add-on-sdk/sdk.js';
import { webSearch, extract, parseUrls, hitsToLines, pagesToLines, linesToBlock } from './api.js';

const KEY_ITEM = 'specstream_api_key';
const $ = (id) => document.getElementById(id);

let key = '';
let hits = [];
let pages = [];
let sandbox = null;
let store = null;

function say(text, bad) {
  $('status').textContent = text || '';
  $('status').className = bad ? 'bad' : '';
}

function show(view) {
  $('key-view').hidden = view !== 'key';
  $('work-view').hidden = view !== 'work';
}

function tab(name) {
  const search = name === 'search';
  $('tab-search').setAttribute('aria-selected', String(search));
  $('tab-extract').setAttribute('aria-selected', String(!search));
  $('search-pane').hidden = !search;
  $('extract-pane').hidden = search;
  say('');
}

function row(parts, checked) {
  const li = document.createElement('li');
  const box = document.createElement('input');
  box.type = 'checkbox';
  box.checked = checked;
  box.setAttribute('aria-label', parts[0][1]);
  const body = document.createElement('div');
  for (const [cls, text] of parts) {
    if (!text) continue;
    const d = document.createElement('div');
    d.className = cls;
    d.textContent = text;
    body.appendChild(d);
  }
  li.append(box, body);
  return li;
}

function ticked(listId, items) {
  const boxes = $(listId).querySelectorAll('input[type=checkbox]');
  return items.filter((_, i) => boxes[i] && boxes[i].checked);
}

async function busy(button, label, work) {
  const old = button.textContent;
  button.disabled = true;
  button.textContent = label;
  try {
    await work();
  } catch (e) {
    say((e && e.message) || 'Something went wrong. Try again.', true);
  } finally {
    button.disabled = false;
    button.textContent = old;
  }
}

async function addToDesign(lines) {
  const block = linesToBlock(lines);
  if (!block.text) {
    say('Tick at least one row first.', true);
    return;
  }
  await sandbox.addTextBlock(block);
  say('Added to your design, with the source URL of every row.');
}

async function start() {
  await addOnUISdk.ready;
  store = addOnUISdk.instance.clientStorage;
  sandbox = await addOnUISdk.instance.runtime.apiProxy('documentSandbox');
  const saved = await store.getItem(KEY_ITEM);
  key = typeof saved === 'string' ? saved : '';
  show(key ? 'work' : 'key');

  $('save-key').addEventListener('click', async () => {
    const k = $('key').value.trim();
    if (!k) {
      say('Paste your SpecStream API key first.', true);
      return;
    }
    key = k;
    await store.setItem(KEY_ITEM, k);
    $('key').value = '';
    say('');
    show('work');
  });

  $('change-key').addEventListener('click', async () => {
    key = '';
    await store.removeItem(KEY_ITEM);
    say('');
    show('key');
  });

  $('tab-search').addEventListener('click', () => tab('search'));
  $('tab-extract').addEventListener('click', () => tab('extract'));

  $('run-search').addEventListener('click', () => busy($('run-search'), 'Searching...', async () => {
    say('');
    hits = await webSearch(fetch.bind(window), key, $('q').value);
    $('hits').replaceChildren(...hits.map((h, i) => row([['t', h.title], ['s', h.snippet], ['u', h.url]], i < 5)));
    $('add-hits').hidden = hits.length === 0;
    say(hits.length ? `${hits.length} results. Tick the rows to add.` : 'No results for this question.');
  }));

  $('add-hits').addEventListener('click', () => busy($('add-hits'), 'Adding...', () =>
    addToDesign(hitsToLines(ticked('hits', hits)))));

  $('run-extract').addEventListener('click', () => busy($('run-extract'), 'Extracting...', async () => {
    say('');
    pages = await extract(fetch.bind(window), key, parseUrls($('urls').value));
    $('pages').replaceChildren(...pages.map((p) => {
      const ok = p.status === 'ok' && !!p.text;
      const size = ok ? `${p.text.length.toLocaleString('en-US')} characters` : `No text (${p.status || 'empty'})`;
      return row([['t', p.title || p.url], ['u', p.url], ['s', size]], ok);
    }));
    $('add-pages').hidden = pages.length === 0;
    say(pages.length ? 'Tick the pages to add.' : 'No pages came back.');
  }));

  $('add-pages').addEventListener('click', () => busy($('add-pages'), 'Adding...', () =>
    addToDesign(pagesToLines(ticked('pages', pages)))));
}

start().catch((e) => say((e && e.message) || 'The add-on could not start. Close it and open it again.', true));
