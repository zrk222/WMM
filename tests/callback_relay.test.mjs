import test from 'node:test';
import assert from 'node:assert/strict';
import {handoff} from '../callback_relay/worker.mjs';

const state='s'.repeat(43), code='C'.repeat(32);
const request=(path,query='')=>({method:'GET',url:`https://relay.example/cb/${path}${query?`?${query}`:''}`});

test('YouTube OAuth metadata is accepted then stripped from the local code handoff',async()=>{
  const response=handoff(request('youtube',new URLSearchParams({state,code,scope:'https://www.googleapis.com/auth/youtube.upload',authuser:'0',prompt:'consent select_account',hd:'example.com'}).toString()));
  assert.equal(response.status,303);
  const target=new URL(response.headers.get('Location'));
  assert.equal(target.origin,'http://127.0.0.1:8765');
  assert.equal(target.pathname,'/social/callback/youtube');
  assert.deepEqual(Object.fromEntries(new URLSearchParams(target.hash.slice(1))),{state,code,error:''});
  assert.deepEqual([...target.searchParams],[]);
});

test('Google callback metadata is provider-specific and rejects duplicates or unknown fields',()=>{
  for(const query of [
    `state=${state}&code=${code}&authuser=0`,
    `state=${state}&code=${code}&unknown=x`,
    `state=${state}&code=${code}&authuser=0&authuser=1`,
    `state=${state}&code=${code}&prompt=none%20consent`,
    `state=${state}&code=${code}&hd=bad%2Fhost`,
  ])assert.equal(handoff(request('linkedin',query)).status,400);
  assert.equal(handoff(request('youtube',`state=${state}&code=${code}&unknown=x`)).status,400);
});

test('OAuth base callbacks retain state/code rules and strict URL checks',()=>{
  const valid=handoff(request('facebook',`state=${state}&code=${code}`));
  assert.equal(valid.status,303);
  for(const url of [
    `https://relay.example/cb/youtube?state=${state}&code=${code}#fragment`,
    `https://user@relay.example/cb/youtube?state=${state}&code=${code}`,
    `https://relay.example/cb/youtube/extra?state=${state}&code=${code}`,
    `https://relay.example/cb/facebook?state=${state}&code=${code}&scope=x`,
  ])assert.equal(handoff({method:'GET',url}).status,400);
});
