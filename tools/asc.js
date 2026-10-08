const crypto=require('crypto'),fs=require('fs'),https=require('https');
// Key ID, issuer and .p8 path come from the environment or the git-ignored .asc.env at the
// repo root -- never from this file, which is public.
const path=require('path');
const envFile=path.join(__dirname,'..','.asc.env');
const conf=Object.assign({},fs.existsSync(envFile)?Object.fromEntries(fs.readFileSync(envFile,'utf8')
  .split('\n').map(l=>l.match(/^\s*([A-Z_]+)=(.*)$/)).filter(Boolean).map(m=>[m[1],m[2].trim()])):{},
  ...['ASC_KEY_ID','ASC_ISSUER_ID','ASC_KEY_PATH'].filter(k=>process.env[k]).map(k=>({[k]:process.env[k]})));
for(const k of ['ASC_KEY_ID','ASC_ISSUER_ID','ASC_KEY_PATH']) if(!conf[k]) throw new Error(k+' missing: set it or add it to .asc.env');
const KEY_ID=conf.ASC_KEY_ID, ISS=conf.ASC_ISSUER_ID;
const pk=fs.readFileSync(conf.ASC_KEY_PATH,'utf8');
function b64u(o){return Buffer.from(typeof o==='string'?o:JSON.stringify(o)).toString('base64').replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');}
function jwt(){const h={alg:'ES256',kid:KEY_ID,typ:'JWT'};const now=Math.floor(Date.now()/1000);
  const p={iss:ISS,iat:now,exp:now+1200,aud:'appstoreconnect-v1'};const s=b64u(h)+'.'+b64u(p);
  const sig=crypto.sign('sha256',Buffer.from(s),{key:pk,dsaEncoding:'ieee-p1363'});
  return s+'.'+sig.toString('base64').replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');}
function api(method,path,body){return new Promise((res,rej)=>{const data=body?JSON.stringify(body):null;
  const req=https.request({host:'api.appstoreconnect.apple.com',path,method,headers:{'Authorization':'Bearer '+jwt(),'Content-Type':'application/json',...(data?{'Content-Length':Buffer.byteLength(data)}:{})}},r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res({status:r.statusCode,body:d}));});
  req.on('error',rej);if(data)req.write(data);req.end();});}
module.exports={api,jwt};
