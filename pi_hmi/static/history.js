/* History reads and exports never issue actuator commands. */
(()=>{
  const el=id=>document.getElementById(id),status=text=>el('history-status').textContent=text;
  let current=null,next=null,loading=false,exporting=false,requestId=null,exportBody=null;
  function selection(){
    const filters={};
    for(const [id,key] of [['experiment','experiment'],['start','start_utc'],['end','end_utc'],['type','type'],['sensor','sensor'],['search','search']]){
      const value=el('history-'+id).value.trim();if(value)filters[key]=value;
    }
    return {resource:el('history-resource').value,filters};
  }
  async function load(advance=false){
    if(loading)return;loading=true;el('history-next').disabled=true;status('Loading history…');
    try{
      if(!advance){current=selection();next=null;}
      const params=new URLSearchParams({...current.filters,limit:'100'});if(advance && next)params.set('cursor',next);
      const response=await fetch('/api/history/'+current.resource+'?'+params);const data=await response.json();
      if(!response.ok)throw Error(data.error || 'History unavailable');
      const area=el('history-rows');area.replaceChildren();
      for(const row of data.rows){
        const article=document.createElement('article');article.className='history-record';
        const title=document.createElement('strong');title.textContent=(row.history_time_utc || 'UTC unknown')+' · '+(row.quality_flag || row.status || row.event_type || row.predicted_class || row.capture_reason || row.action || 'Saved record');article.append(title);
        const summary=document.createElement('p');
        summary.textContent=[row.name,row.sensor_id,row.value==null ? null : String(row.value)+' '+(row.unit || 'unit unknown'),row.requested_state,row.component,row.source_quality==='legacy_unknown' ? 'Source unknown' : null].filter(v=>v!=null).join(' · ');
        article.append(summary);
        if(current.resource==='images'){
          const link=document.createElement('a');link.href='/api/history/images/'+row.image_id+'/file';link.textContent='View saved JPEG (verified on request)';link.target='_blank';link.rel='noopener';article.append(link);
        }
        const disclosure=document.createElement('details'),label=document.createElement('summary');label.textContent='Record details and provenance';
        const details=document.createElement('pre');details.textContent=JSON.stringify(row,null,2);disclosure.append(label,details);article.append(disclosure);area.append(article);
      }
      next=data.next_cursor;status(data.rows.length ? data.rows.length+' durable records · '+data.consistency : 'No matching records');
    }catch(error){el('history-rows').replaceChildren();next=null;status('History unavailable: '+error.message);}
    finally{loading=false;el('history-next').disabled=!next;}
  }
  async function watch(id){
    const response=await fetch('/api/exports/'+id),job=await response.json();if(!response.ok)throw Error(job.error || 'Export status unavailable');
    const result=job.result;sessionStorage.setItem('germ-history-export',id);
    el('export-retry').hidden=!['failed','interrupted'].includes(job.status) || job.attempt>=3;
    el('export-status').textContent='Export '+id+' · '+job.status+(job.error ? ' · '+job.error : '')+(result ? ' · '+result.rows+' rows · '+result.image_errors.length+' image errors · SHA-256 '+result.sha256 : ' · completion not yet acknowledged');
    if(job.download_url){el('export-download').href=job.download_url;el('export-download').hidden=false;el('export-download').textContent=job.status==='complete_with_errors' ? 'Download partial archive — inspect image errors in manifest' : 'Download verified complete archive';}
    if(['queued','running'].includes(job.status)){setTimeout(()=>watch(id).catch(finishError),500);return;}
    exporting=false;requestId=null;exportBody=null;
  }
  function finishError(error){exporting=false;el('export-status').textContent='Export unavailable: '+error.message+' · retry uses the same request identity; no completion claimed';}
  async function start(all){
    if(exporting)return;
    if(!exportBody){
      const selected=selection();
      if(all && selected.filters.sensor){finishError(Error('Clear sensor filter before exporting all record types'));return;}
      requestId=crypto.randomUUID();exportBody={request_id:requestId,definition:{filters:selected.filters,strict_images:el('export-strict').checked}};
      if(!all)exportBody.definition.resources=[selected.resource];
    }
    exporting=true;el('export-download').hidden=true;el('export-status').textContent='Export requested · waiting for durable job receipt';
    try{
      const response=await fetch('/api/exports',{method:'POST',headers:{'Content-Type':'application/json','X-GERM-Token':controlToken},body:JSON.stringify(exportBody)});
      const job=await response.json();if(!response.ok)throw Error(job.error || 'Export request unavailable');await watch(requestId);
    }catch(error){finishError(error);}
  }
  el('history-form').onsubmit=event=>{event.preventDefault();load();};el('history-next').onclick=()=>load(true);
  el('export-history').onclick=()=>start(false);el('export-all').onclick=()=>start(true);load();
  el('export-retry').onclick=async()=>{
    const id=sessionStorage.getItem('germ-history-export');if(!id || exporting)return;
    exporting=true;el('export-retry').hidden=true;
    try{
      const response=await fetch('/api/exports/'+id+'/retry',{method:'POST',headers:{'Content-Type':'application/json','X-GERM-Token':controlToken},body:JSON.stringify({retry:true})});
      const result=await response.json();if(!response.ok)throw Error(result.error || 'Retry unavailable');await watch(id);
    }catch(error){finishError(error);}
  };
  const previous=sessionStorage.getItem('germ-history-export');if(previous)watch(previous).catch(finishError);
})();
