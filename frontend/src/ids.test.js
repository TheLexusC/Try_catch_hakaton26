import {test} from 'node:test';
import assert from 'node:assert/strict';
import {newId} from './ids.js';
test('creation IDs work without randomUUID and in an insecure HTTP context',()=>{
  const previous=Object.getOwnPropertyDescriptor(globalThis,'crypto');
  try{
    Object.defineProperty(globalThis,'crypto',{configurable:true,value:undefined});
    const ids=new Set(Array.from({length:100},()=>newId('h')));
    assert.equal(ids.size,100);
    for(const id of ids)assert.match(id,/^h-[a-f0-9]{24}$/);
  }finally{if(previous)Object.defineProperty(globalThis,'crypto',previous);else delete globalThis.crypto;}
});
