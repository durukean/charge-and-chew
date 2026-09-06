const crypto=require('crypto'),fs=require('fs'),https=require('https');
const KEY_ID='63U8C63MW7', ISS='b8ade631-2e77-4eb4-81f9-2bd3c20ca355';
const pk=fs.readFileSync('/Users/durukan/Downloads/AuthKey_63U8C63MW7.p8','utf8');
function b64u(o){return Buffer.from(typeof o==='string'?o:JSON.stringify(o)).toString('base64').replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');}
function jwt(){const h={alg:'ES256',kid:KEY_ID,typ:'JWT'};const now=Math.floor(Date.now()/1000);
  const p={iss:ISS,iat:now,exp:now+1200,aud:'appstoreconnect-v1'};const s=b64u(h)+'.'+b64u(p);
  const sig=crypto.sign('sha256',Buffer.from(s),{key:pk,dsaEncoding:'ieee-p1363'});
  return s+'.'+sig.toString('base64').replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');}
function api(method,path,body){return new Promise((res,rej)=>{const data=body?JSON.stringify(body):null;
  const req=https.request({host:'api.appstoreconnect.apple.com',path,method,headers:{'Authorization':'Bearer '+jwt(),'Content-Type':'application/json',...(data?{'Content-Length':Buffer.byteLength(data)}:{})}},r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res({status:r.statusCode,body:d}));});
  req.on('error',rej);if(data)req.write(data);req.end();});}
module.exports={api,jwt};
