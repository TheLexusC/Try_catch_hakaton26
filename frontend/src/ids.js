// Object IDs are not credentials. This also works on ordinary HTTP LAN addresses.
export function newId(prefix='o'){
  const bytes=new Uint8Array(12);
  if(globalThis.crypto?.getRandomValues)globalThis.crypto.getRandomValues(bytes);
  else for(let i=0;i<bytes.length;i++)bytes[i]=Math.floor(Math.random()*256);
  return prefix+'-'+Array.from(bytes,n=>n.toString(16).padStart(2,'0')).join('');
}
