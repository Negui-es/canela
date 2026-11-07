const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../templates/pwa/service-worker.js'),'utf8')
  .replace('{{ cache_name|escapejs }}','canela-offline-test')
  .replace('{{ languages|safe }}',JSON.stringify(['es','en','fr','de','it']));

function harness(fetchImpl=async()=>new Response('private content')) {
  const handlers={},stored=new Map(),requests=[],deleted=[];
  const cache={async addAll(items){for(const item of items){requests.push(item);stored.set(item.url,new Response('generic offline '+item.url));}},async match(url){return stored.get(url)?.clone();}};
  const self={location:{origin:'https://canela.example'},navigator:{languages:['fr-FR','en']},clients:{async claim(){}},async skipWaiting(){},addEventListener(name,handler){handlers[name]=handler;}};
  const caches={async open(){return cache;},async keys(){return ['canela-offline-old','unrelated-cache','canela-offline-test'];},async delete(key){deleted.push(key);}};
  vm.runInNewContext(source,{self,caches,fetch:fetchImpl,Request:class{constructor(url,options){this.url=url;Object.assign(this,options);}},Response,URL,AbortController,setTimeout,clearTimeout});
  const dispatch=async(name,props={})=>{let promise;handlers[name]({...props,waitUntil(p){promise=p;},respondWith(p){promise=p;}});return promise ? await promise : undefined;};
  const navigate=(url='/en/pieces/')=>({request:{url:'https://canela.example'+url,method:'GET',mode:'navigate'}});
  return {dispatch,navigate,stored,requests,deleted,self};
}

test('precache contains only five anonymous generic offline documents',async()=>{
  const h=harness();await h.dispatch('install');
  assert.deepEqual([...h.stored.keys()],['es','en','fr','de','it'].map(code=>'/offline/'+code+'/'));
  assert.ok(h.requests.every(request=>request.credentials==='omit'&&request.redirect==='error'));
  await h.dispatch('activate');assert.deepEqual(h.deleted,['canela-offline-old']);
});
test('successful private navigations are network only and never enter the cache',async()=>{
  let options;const h=harness(async(request,opts)=>{options=opts;return new Response('private notes');});
  await h.dispatch('install');const response=await h.dispatch('fetch',h.navigate());
  assert.equal(await response.text(),'private notes');assert.equal(options.cache,'no-store');assert.equal(h.stored.size,5);
  assert.ok([...h.stored.values()].every(value=>value.status===200));
});
test('network failure uses the URL language and returns 503 without private content',async()=>{
  const h=harness(async()=>{throw new Error('offline');});await h.dispatch('install');
  const response=await h.dispatch('fetch',h.navigate('/de/stuecke/'));
  assert.equal(response.status,503);assert.equal(await response.text(),'generic offline /offline/de/');
  assert.equal(response.headers.get('Cache-Control'),'no-store');
});
test('unprefixed offline entry follows browser preference, with English fallback',async()=>{
  const h=harness(async()=>{throw new Error('offline');});await h.dispatch('install');
  assert.equal(await (await h.dispatch('fetch',h.navigate('/'))).text(),'generic offline /offline/fr/');
  h.self.navigator.languages=['ja'];assert.equal(await (await h.dispatch('fetch',h.navigate('/'))).text(),'generic offline /offline/en/');
});
test('forms, uploads, HTMX requests and external URLs are never intercepted or queued',async()=>{
  let fetched=false;const h=harness(async()=>{fetched=true;});
  for(const request of [
    {url:'https://canela.example/en/pieces/new/',method:'POST',mode:'navigate'},
    {url:'https://canela.example/fotos/private/',method:'GET',mode:'cors'},
    {url:'https://canela.example/en/pieces/',method:'GET',mode:'cors'},
    {url:'https://external.example/',method:'GET',mode:'navigate'},
  ])assert.equal(await h.dispatch('fetch',{request}),undefined);
  assert.equal(fetched,false);assert.equal(h.stored.size,0);
});
test('application errors and Cloudflare offline HTML are preserved exactly',async()=>{
  for(const status of [400,401,403,404,429,500,503]){
    const original=new Response('original response',{status});const h=harness(async()=>original);
    assert.equal(await h.dispatch('fetch',h.navigate()),original);
  }
});
