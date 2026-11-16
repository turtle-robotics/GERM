/* Storage artifacts are offline copies. No actuator command is issued here. */
(()=>{
  const el=id=>document.getElementById(id),size=n=>typeof n==='number'?(n/1048576).toFixed(2)+' MiB':'unknown';
  let busy=false,authorized=false,readyFor=null,pending=null,lastId=null;
  async function inventory(){
    try{
      const response=await fetch('/api/storage'),data=await response.json();if(!response.ok)throw Error(data.error || 'Storage unavailable');
      const v=data.volume;
      el('storage-capacity').textContent=v.free_bytes==null?'Volume measurement unavailable':`Observed host volume: ${size(v.used_bytes)} used / ${size(v.total_bytes)} total · ${size(v.free_bytes)} free · ${v.utilization_percent}% utilized${data.capacity_warning?' · CAPACITY WARNING · no deletion':''}`;
      const area=el('storage-inventory');area.replaceChildren();
      for(const [name,item] of Object.entries(data.categories)){
        const line=document.createElement('div');line.className='storage-usage';line.textContent=name+': '+size(item.logical_bytes)+' in '+item.files+' files · '+(item.complete?'observed logical sizes':'INCOMPLETE INVENTORY · '+item.errors.join('; '));area.append(line);
      }
      const e=data.backup_estimate;el('storage-estimate').textContent=e.estimated_required_free_bytes==null?'Backup estimate unavailable':`Estimated working free-space requirement: ${size(e.estimated_required_free_bytes)} · ${e.image_count} indexed images · estimate does not prove files exist`;
      const selected=el('storage-source').value;el('storage-source').replaceChildren(new Option('Select a backup',''));
      for(const job of data.jobs.filter(j=>j.definition.kind==='backup'))el('storage-source').append(new Option(job.request_id+' · '+job.status,job.request_id));
      el('storage-source').value=selected;
      authorized=document.body.dataset.storageAuthorized==='true';updateButtons();
    }catch(error){
      el('storage-capacity').textContent='Storage unavailable: '+error.message;el('storage-estimate').textContent='Estimate unavailable';el('storage-inventory').replaceChildren();
      authorized=false;updateButtons();
    }
  }
  function updateButtons(){
    const selected=el('storage-source').value;
    el('storage-backup').disabled=!authorized || busy;
    el('storage-verify').disabled=!authorized || busy || !selected;el('storage-preflight').disabled=!authorized || busy || !selected;
    el('storage-restore').disabled=!authorized || busy || !selected || readyFor!==selected;
  }
  async function watch(id){
    const response=await fetch('/api/storage/jobs/'+id),job=await response.json();if(!response.ok)throw Error(job.error || 'Job receipt unavailable');
    lastId=id;sessionStorage.setItem('germ-storage-job',id);
    el('storage-job-status').textContent=job.definition.kind+' · '+job.status+' · attempt '+job.attempt+(job.error?' · '+job.error:'')+(job.result?.kind==='restore' && job.result.status==='complete'?' · offline copy verified; running system unchanged':'');
    el('storage-report').textContent=JSON.stringify(job.result || {completion:'Not durably acknowledged'},null,2);
    el('storage-download').hidden=!job.download_url;if(job.download_url)el('storage-download').href=job.download_url;
    el('storage-retry').hidden=!['failed','interrupted','incomplete'].includes(job.status) || job.attempt>=3;
    if(['queued','running'].includes(job.status)){busy=true;updateButtons();setTimeout(()=>watch(id).catch(failed),500);return;}
    if(job.definition.kind==='preflight')readyFor=job.result?.valid?job.definition.backup_id:null;
    if(job.definition.kind==='verify' && !job.result?.valid)readyFor=null;
    busy=false;pending=null;await inventory();
  }
  function failed(error){busy=false;el('storage-job-status').textContent='Storage operation unavailable: '+error.message+' · no completion claimed';updateButtons();}
  async function start(kind){
    if(busy)return;
    if(kind==='restore' && !confirm('Create a new isolated offline restore? The running database and images will remain unchanged. No hardware will be activated.'))return;
    if(!pending){const definition={kind};if(kind!=='backup')definition.backup_id=el('storage-source').value;pending={request_id:crypto.randomUUID(),definition};}
    busy=true;updateButtons();el('storage-download').hidden=true;el('storage-report').textContent='No durable result for the current request';el('storage-job-status').textContent='Request queued locally · waiting for durable job receipt';
    try{
      const response=await fetch('/api/storage/jobs',{method:'POST',headers:{'Content-Type':'application/json','X-GERM-Token':controlToken},body:JSON.stringify(pending)});
      const data=await response.json();if(!response.ok)throw Error(data.error || 'Storage operation refused');await watch(pending.request_id);
    }catch(error){failed(error);}
  }
  document.body.dataset.storageAuthorized=el('storage-backup').disabled?'false':'true';
  el('storage-refresh').onclick=inventory;el('storage-source').onchange=()=>{readyFor=null;updateButtons();};
  for(const kind of ['backup','verify','preflight','restore'])el('storage-'+kind).onclick=()=>start(kind);
  el('storage-retry').onclick=async()=>{
    if(!lastId || busy)return;busy=true;updateButtons();
    try{
      const response=await fetch('/api/storage/jobs/'+lastId+'/retry',{method:'POST',headers:{'Content-Type':'application/json','X-GERM-Token':controlToken},body:JSON.stringify({retry:true})});
      const data=await response.json();if(!response.ok)throw Error(data.error || 'Retry refused');await watch(lastId);
    }catch(error){failed(error);}
  };
  inventory();const previous=sessionStorage.getItem('germ-storage-job');if(previous)watch(previous).catch(failed);
})();
