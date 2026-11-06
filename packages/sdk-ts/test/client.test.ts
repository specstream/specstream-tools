import assert from "node:assert/strict";
import test from "node:test";
import { Client, FAMILIES, assertFamily } from "../dist/index.js";

const approval = { quote_id: "cqt_fixture", quote_hash: "a".repeat(64), confirm_max_cents: 900, idempotency_key: "reviewed-request-001" };

test("supported public targets are broad and canonical", () => {
  assert.equal(FAMILIES.length, new Set(FAMILIES).size);
  for (const target of ["software_repository", "dataset", "organization", "grant"]) assert.ok(FAMILIES.includes(target));
  assert.ok(!FAMILIES.includes("company"));
});

test("any kind name is a valid entity_type", () => {
  assert.equal(assertFamily("organization"), "organization");
  assert.equal(assertFamily("wine_estate"), "wine_estate");
  assert.throws(() => assertFamily("  "));
});

test("obsolete spending and sample methods do not exist", () => {
  const client = new Client({ apiKey: "fixture-key" });
  for (const name of ["quote", "confirm", "run", "createFind", "continueFind", "startSpecFind"]) assert.ok(!(name in client), name);
});

test("an exact signed authorization is required before any HTTP", () => {
  let calls = 0;
  const client = new Client({ apiKey: "fixture-key", fetch: async () => { calls++; throw Error("No HTTP expected"); } });
  for (const invalid of [null, undefined, true, "900", -1, 1.2, NaN, Infinity]) {
    assert.throws(() => client.authorizeCapacityWork({ ...approval, confirm_max_cents: invalid }));
  }
  assert.throws(() => client.authorizeCapacityWork({quote_id: "cqt_fixture", quote_hash: "a".repeat(64)}));
  assert.throws(() => client.authorizeCapacityWork({...approval, unreviewed: true}));
  assert.equal(calls,0);
});

test("compile, quote, explicit approval and request recovery preserve the exact operation", async () => {
  const calls: {method:string,url:string,body:unknown}[] = [];
  const client = new Client({apiKey:"fixture-key",fetch:async(url,init)=>{
    const body=init?.body?JSON.parse(String(init.body)):null;
    calls.push({method:init?.method||"GET",url:String(url),body});
    const data=String(url).endsWith('/parse')?{ast_hash:'b'.repeat(64),ast:{entity_type:'grant'}}:
      String(url).endsWith('/quotes')?{quote_id:approval.quote_id,quote_hash:approval.quote_hash,maximum_cents:900}:
      {find_id:'fnd_fixture',state:'running'};
    return new Response(JSON.stringify({data}),{status:200});
  }});
  const parsed=await client.compile('grants with open deadlines');
  await client.quoteCapacityWork({ast_hash:parsed.ast_hash,operation:'find',requested_units:5});
  assert.equal(calls.length,2);
  assert.equal((await client.authorizeCapacityWork(approval)).find_id,'fnd_fixture');
  assert.deepEqual(calls[2].body,approval);
  assert.equal((await client.getCapacityRequest(approval.idempotency_key)).find_id,'fnd_fixture');
  assert.ok(calls[3].url.endsWith('/requests/reviewed-request-001'));
  assert.ok(calls.every(call=>!call.url.endsWith('/run')&&!call.url.endsWith('/funding')));
});

test("continuation quote is not execution and pages expose the real cursor", async () => {
  const calls: {url:string,body:unknown}[]=[];
  const client=new Client({apiKey:'fixture-key',fetch:async(url,init)=>{
    calls.push({url:String(url),body:init?.body?JSON.parse(String(init.body)):null});
    return new Response(JSON.stringify({data:{rows:[],next_cursor:null}}));
  }});
  const scope={ast_hash:'b'.repeat(64),operation:'refresh',parent_find_id:'fnd_parent',requested_units:25};
  await client.quoteCapacityWork(scope);
  assert.deepEqual(calls[0].body,scope);
  await client.rows('fnd/a','opaque?&page',17);
  assert.equal(new URL(calls[1].url).pathname,'/v1/finds/fnd%2Fa/rows');
  assert.deepEqual(Object.fromEntries(new URL(calls[1].url).searchParams),{limit:'17',cursor:'opaque?&page'});
  for(const bad of [0,101,true,1.5,'2']) assert.throws(()=>client.rows('fnd/a',null,bad));
  assert.equal(calls.length,2);
});

test("webSearch returns the answer's kind and sources", async () => {
  const urls: string[] = [];
  const page = {request_id:"call-1",kind:"fact",answer:{value:"2006",page:"https://example.org/a"},rows:[],
    sources:[{url:"https://example.org/a",title:"A",site:"example.org",snippet:"",cited:true}]};
  const client = new Client({apiKey:"fixture-key",fetch:async(url)=>{
    urls.push(String(url));
    return new Response(JSON.stringify({data:page}),{status:200});
  }});
  const found = await client.webSearch({q:"when was A founded"});
  assert.ok(urls[0].endsWith("/v1/web-search?q=when+was+A+founded"));
  assert.equal(found.kind,"fact");
  assert.deepEqual(found.sources,page.sources);
});
