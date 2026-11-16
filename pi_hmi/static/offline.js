/* Local host status only. No cloud, offline command queue or permission cache. */
(()=>{
  const el=id=>document.getElementById(id);let checking=false,managed=false;
  document.querySelector('nav a.active')?.setAttribute('aria-current','page');
  const dialog=el('confirm-dialog');
  dialog?.addEventListener('cancel',()=>{el('command-feedback').textContent='Command cancelled · nothing was sent';});
  function disconnected(){
    el('local-connection').textContent='Local service connection unavailable · current status unknown';
    el('service-health').textContent='Stored values and old permissions must not be treated as current.';
    el('recover-services').disabled=true;
    el('service-guidance').textContent='Reconnect to this local host. Internet access is not needed. No commands are queued or replayed.';
  }
  async function check(){
    if(checking)return;checking=true;
    try{
      const response=await fetch('/api/services',{cache:'no-store'}),data=await response.json();
      if(data.state==='not_configured'){
        managed=false;el('local-connection').textContent='Local HMI connected · no managed host runtime · internet is not required';
        el('service-health').textContent='Default restricted mode; managed services are not configured.';el('recover-services').disabled=true;return;
      }
      if(!response.ok)throw Error(data.error || 'Host status unavailable');managed=true;
      el('local-connection').textContent='Local host '+data.state+' · '+data.readiness+' · internet is not required';
      el('service-health').textContent=Object.entries(data.components).map(([name,item])=>name.replaceAll('_',' ')+': '+item.state).join(' · ')+` · camera ${data.camera.state} · model ${data.model_state} · ${data.sensor_state}`;
      el('service-guidance').textContent=data.recovery_instruction;
      const authorized=typeof latestState!=='undefined' && latestState?.control_boundary?.enabled===true;
      el('recover-services').disabled=!authorized || ['recovering','stopping'].includes(data.state);
    }catch{disconnected();}
    finally{checking=false;}
  }
  el('recover-services').onclick=async()=>{
    if(!managed || !confirm('Recover synthetic host services? Existing permissions and confirmations are discarded. Schedules stay inhibited and require a separate reviewed action.'))return;
    el('recover-services').disabled=true;el('service-health').textContent='Recovering dependencies · no permissions restored';
    try{
      const response=await fetch('/api/services/recover',{method:'POST',headers:{'Content-Type':'application/json','X-GERM-Token':controlToken},body:'{}'});
      const result=await response.json();if(!response.ok)throw Error(result.error || result.state || 'Recovery failed');
      el('command-feedback').textContent='Host recovery completed · permissions not restored · recheck current inputs';
    }catch(error){el('command-feedback').textContent='Recovery unavailable: '+error.message;}
    finally{await check();}
  };
  window.addEventListener('offline',()=>{disconnected();if(typeof pollState==='function')pollState();});
  window.addEventListener('online',()=>{check();if(typeof pollState==='function')pollState();});
  check();setInterval(check,2000);
})();
