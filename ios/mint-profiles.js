// Mint (or re-mint) the App Store provisioning profiles through the App Store Connect API
// and install them where xcodebuild looks. Run when a profile expires, the distribution
// certificate changes, or a new bundle id (extension) is added.
//
//   node ios/mint-profiles.js
//
// Why not automatic signing: cloud signing with the ASC API key cannot create distribution
// profiles ("Cloud signing permission error"), and "automatic" export has no Xcode account
// to ask. Profiles minted here plus ExportOptions.plist (signingStyle: manual) sidestep both.
const {api}=require('../tools/asc.js'); const fs=require('fs'); const os=require('os'); const path=require('path');
const TEAM='T37B6B6S7K';
const WANT=[['CC App Store','com.chargeandchew.app'],['CC Widget App Store','com.chargeandchew.app.widget']];
(async()=>{
  const dir=path.join(os.homedir(),'Library/MobileDevice/Provisioning Profiles'); fs.mkdirSync(dir,{recursive:true});
  let r=await api('GET','/v1/certificates?filter[certificateType]=DISTRIBUTION&limit=5');
  const certIds=JSON.parse(r.body).data.filter(c=>new Date(c.attributes.expirationDate)>new Date()).map(c=>c.id);
  if(!certIds.length) throw new Error('no valid Apple Distribution certificate on the account');
  for (const [name,ident] of WANT){
    r=await api('GET','/v1/bundleIds?filter[identifier]='+ident+'&filter[platform]=IOS');
    let bid=(JSON.parse(r.body).data||[]).find(b=>b.attributes.identifier===ident);
    if(!bid){ r=await api('POST','/v1/bundleIds',{data:{type:'bundleIds',attributes:{identifier:ident,name:name.replace(/ App Store$/,''),platform:'IOS',seedId:TEAM}}}); bid=JSON.parse(r.body).data; }
    r=await api('GET','/v1/profiles?filter[name]='+encodeURIComponent(name));
    for (const p of (JSON.parse(r.body).data||[])) await api('DELETE','/v1/profiles/'+p.id);
    let prof=null;
    for (let i=0;i<3&&!prof;i++){   // the API occasionally answers 500 on create; retry
      r=await api('POST','/v1/profiles',{data:{type:'profiles',attributes:{name,profileType:'IOS_APP_STORE'},
        relationships:{bundleId:{data:{type:'bundleIds',id:bid.id}},certificates:{data:certIds.map(id=>({type:'certificates',id}))}}}});
      const j=JSON.parse(r.body); if(!j.errors) prof=j.data; else { console.log(name,'attempt',i+1,j.errors[0].code); await new Promise(x=>setTimeout(x,3000)); }
    }
    if(!prof) throw new Error('could not create '+name);
    fs.writeFileSync(path.join(dir,prof.attributes.uuid+'.mobileprovision'),Buffer.from(prof.attributes.profileContent,'base64'));
    console.log('installed',name,prof.attributes.uuid,prof.attributes.profileState);
  }
})().catch(e=>{console.error(e.message);process.exit(1);});
