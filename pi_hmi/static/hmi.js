/* Local-only HMI. Every hardware, SQL, and ML request goes through Flask. */
const page = document.body.dataset.page;
const byId = id => document.getElementById(id);
const setText = (id, text) => { const node = byId(id); if (node) node.textContent = text; };
let latestState = null;
let latestGrow = null;
let scheduleEditorCycle = null;
let latestMedia = null;
let displayedImageKey = null;
let mediaFormInitialized = false;
let mediaBusy = false;
let captureBusy = false;
let lastCaptureFailed = false;
let analysisRequestId = null;

function clock() {
  setText('clock', new Intl.DateTimeFormat(undefined, {hour:'numeric', minute:'2-digit'}).format(new Date()));
}
clock(); setInterval(clock, 30000);

const camera = byId('camera-image');
if (camera) {
  const refresh = () => { camera.src = '/camera.jpg?t=' + Date.now(); };
  camera.onload = () => { camera.hidden=false;byId('camera-status').hidden = true; setTimeout(refresh, 200); };
  camera.onerror = () => { camera.hidden=true;byId('camera-status').hidden = false; setTimeout(refresh, 1200); };
  refresh();
}

function sensorText(reading) {
  const detail = reading?.fault_reason?.replaceAll('_',' ') || 'Unavailable';
  if (!reading || reading.state === 'unavailable' || reading.value === null || reading.value === undefined)
    return ['NO DATA', (reading?.quality_flag === 'stale' ? 'STALE · value withheld · ' : '') + detail];
  if (typeof reading.value === 'boolean') return [reading.safe === true ? 'SAFE' : reading.safe === false ? 'UNSAFE' : String(reading.value), 'Normalized input · ' + reading.source];
  const value = Number.isInteger(reading.value) ? reading.value : Number(reading.value).toFixed(1);
  const unit = reading.unit === '%RH' ? '%' : reading.unit;
  if (reading.state === 'stale') return [`${value} ${unit}`, `STALE · ${reading.age_seconds}s old`];
  if (reading.quality_flag === 'suspect') return [`${value} ${unit}`, 'Unvalidated context · not control input'];
  return [`${value} ${unit}`, `${latestState?.data_scope === 'simulation' ? 'SIMULATED' : 'LIVE'} · ${reading.source} · ${reading.timestamp_utc || 'sample time unknown'}`];
}

function renderSensor(id, reading) {
  const [value, detail] = sensorText(reading);
  setText(id + '-value', value);
  setText(id + '-state', detail);
}

function actuatorText(item) {
  if (!item || item.state === 'unavailable') return 'Arduino unavailable';
  if (item.state === 'reported') {
    if (item.mode === 'rainbow') return 'Rainbow · firmware reported';
    if (Array.isArray(item.reported_state)) return `RGB ${item.reported_state.join(', ')} · firmware reported`;
    if (Number.isInteger(item.speed)) return `PWM ${item.speed}/255 · firmware reported`;
    return `${item.reported_state ? 'ON' : 'OFF'} · firmware reported`;
  }
  if (item.last_request === null) return 'State unverified';
  if (Array.isArray(item.last_request)) return 'RGBW requested · unverified';
  if (typeof item.last_request === 'object') return `Speed ${item.last_request.speed} requested`;
  return `${String(item.last_request).toUpperCase()} requested · unverified`;
}

function renderML(ml) {
  const result = ml && ml.latest_result;
  if (!result) {
    const state = ml?.state;
    const labels = {
      running:['Inference running','Processing latest image'],
      error:['ML unavailable','Inference service error'],
      unavailable:['ML unavailable','Inference service offline'],
      not_configured:['Awaiting ML service','No inference available'],
      timed_out:['Inference timed out','Late results are discarded; no diagnosis'],
    };
    const [title, detail] = labels[state] || ['No ML result yet','Waiting for first analysis'];
    setText('ml-class', title);
    setText('ml-detail', detail);
    return;
  }
  const low = result.review_required || result.predicted_class === 'uncertain';
  const historical=result.stale || !['ready','completed'].includes(ml.state);
  setText('ml-class', (historical ? 'Previous result · ' : '') + (low ? 'Uncertain / review required' : result.predicted_class) + (result.scope==='synthetic-contract-only' ? ' · SYNTHETIC TEST' : ''));
  const confidence = typeof result.confidence === 'number' ?
    `${(result.confidence * 100).toFixed(1)}% confidence` : 'confidence unavailable';
  setText('ml-detail', `${confidence} · ${result.model_version || 'model unknown'} · ${result.timestamp_utc || 'time unavailable'} · image age ${result.age_seconds ?? 'unknown'} s · model ${ml.state} · trace ${result.event_status || 'unknown'}${result.scope==='synthetic-contract-only' ? ' · not a plant diagnosis' : ''}`);
}

function statusRows(items) {
  const fragment = document.createDocumentFragment();
  for (const [name, value] of items) {
    const row = document.createElement('div'); row.className = 'status-row';
    const label = document.createElement('strong'); label.textContent = name;
    const detail = document.createElement('span'); detail.textContent = value;
    row.append(label, detail); fragment.append(row);
  }
  return fragment;
}

function renderState(data) {
  latestState = data;
  const enabled = data.control_boundary?.enabled === true;
  setText('boundary-status', data.control_boundary?.state === 'simulation' ? 'SIMULATION — NO HARDWARE' : 'Controls restricted — production boundary not approved');
  const banner = byId('maintenance-banner');
  if (banner) { banner.hidden = !data.maintenance_banner; banner.textContent = data.maintenance_banner || ''; }
  setText('inhibit-status', (data.inhibits || []).length ? 'Inhibits: ' + data.inhibits.map(x => x.replaceAll('_',' ').replaceAll(':',' · ')).join(', ') : 'Checks valid; commands still require server permission');
  document.querySelectorAll('[data-workflow]').forEach(button => button.disabled = !enabled);
  const state = byId('system-state');
  state.textContent = data.system_state;
  state.className = 'state-pill ' + data.system_state.toLowerCase();
  setText('arduino-head', 'Arduino: ' + data.arduino.state);
  for (const name of ['air_temperature','humidity','water_temperature','electronics_temperature','water_level','door']) renderSensor(name, data.sensors[name]);
  setText('home-estop', 'E-stop: ' + data.estop + ' · physical monitoring not commissioned');
  setText('maintenance-estop', 'E-stop: ' + data.estop + ' · simulation input only');
  const alarm=data.alerts.highest;
  setText('highest-alert', data.alerts.active === null ? 'Highest alarm unknown · database unavailable' : alarm ? `Highest alarm: ${alarm.severity} · ${alarm.message}` : 'No active alarms recorded');
  renderGrow(data.grow,enabled,data.operating_state?.logging);
  renderML(data.ml);
  document.querySelectorAll('.camera-badge').forEach(badge=>badge.textContent=data.camera.state==='ready' ? (data.camera.source==='synthetic' || data.data_scope==='simulation' ? 'SYNTHETIC CAMERA' : 'LIVE CAMERA') : 'CAMERA '+data.camera.state.toUpperCase());
  if(camera && data.camera.state!=='ready') {camera.hidden=true;byId('camera-status').hidden=false;byId('camera-status').textContent='Camera '+data.camera.state;}
  renderMedia(data.media,enabled);
  for (const name of ['lighting','fan','pump']) {
    setText(name + '-status', actuatorText(data.actuators[name]));
    setText(name + '-detail', actuatorText(data.actuators[name]));
  }
  const active = data.alerts.active;
  setText('alert-count', active === null ? 'Count unknown · SQL pending' :
    `${active.length} active`);
  if (page === 'maintenance') {
    const sensors = byId('maintenance-sensors'); sensors.replaceChildren(statusRows([
      ['Air temperature', sensorText(data.sensors.air_temperature)[1]],
      ['Humidity', sensorText(data.sensors.humidity)[1]],
      ['Water temperature', 'Not installed'],
      ['Arduino A0', sensorText(data.sensors.arduino_a0)[1]],
    ]));
    const connections = byId('maintenance-connections'); connections.replaceChildren(statusRows([
      ['Arduino', data.arduino.state], ['AI Camera', data.camera.state],
      ['Database', data.database.state], ['ML', data.ml.state],
    ]));
  }
  if (page === 'settings') {
    setText('settings-model', 'ML model: ' + (data.ml.model?.model_version || 'not configured'));
  }
  if (page === 'controls') {
    const offline = !enabled || !data.operating_state?.controller_connected;
    document.querySelectorAll('[data-command]').forEach(button => button.disabled = offline);
  }
}

async function pollState() {
  try {
    const response = await fetch('/api/state', {cache:'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderState(await response.json());
  } catch (error) {
    const state = byId('system-state');
    state.textContent = 'STATUS UNAVAILABLE'; state.className = 'state-pill critical';
    setText('arduino-head', 'Backend unavailable');
    for (const name of ['air_temperature','humidity','water_temperature','electronics_temperature','water_level','door']) {
      setText(name + '-value', 'NO DATA'); setText(name + '-state', 'Backend unavailable');
    }
    setText('alert-count', 'Count unknown');
    setText('ml-class', 'ML status unavailable');
    setText('ml-detail', 'Backend unavailable');
    for (const name of ['lighting','fan','pump']) {
      setText(name + '-status', 'Backend unavailable');
      setText(name + '-detail', 'Backend unavailable');
    }
    document.querySelectorAll('[data-command],[data-workflow],#create-cycle,#save-schedules,#recover-grow,#capture-button,#analyze-button,#save-capture-schedule,#recover-captures,#recover-camera-clock').forEach(button => button.disabled = true);
    setText('capture-clock-status','Scheduling state unknown · backend unavailable');
    setText('camera-metadata','Camera status unknown · backend unavailable');
    setText('model-status','Model status unknown · backend unavailable');
    setText('grow-summary','Grow cycle unavailable · backend offline');
    setText('logging-summary','Event persistence unknown · backend offline');
    setText('home-estop','E-stop input unknown · backend unavailable');
    setText('highest-alert','Highest alarm unknown · backend unavailable');
    setText('last-maintenance','Last maintenance unavailable');
    setText('home-light-schedule','Light schedule unavailable');
    setText('home-mist-schedule','Mist schedule unavailable');
    setText('home-grow-day','Grow day unavailable');
    setText('inhibit-status', 'Backend unavailable — last known maintenance indication retained');
  }
}
pollState(); setInterval(pollState, 2000);

if (page === 'controls') {
  byId('lighting-upload').disabled = true;
  setText('lighting-upload-status', 'Firmware updates restricted pending safety and deployment review');
  for (const key of ['r','g','b','w']) {
    const slider = byId('led-' + key);
    slider.addEventListener('input', () => setText('led-' + key + '-value', slider.value));
  }
  byId('fan-speed').addEventListener('input', event => setText('fan-speed-value', event.target.value));
  const dialog = byId('confirm-dialog');
  let pending = null;
  byId('cancel-command').onclick = () => dialog.close();
  byId('accept-command').onclick = async () => {
    dialog.close(); if (!pending) return;
    const {url, payload, target} = pending; pending = null;
    try {
      const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json', 'X-GERM-Token':controlToken}, body:JSON.stringify(payload)});
      const result = await response.json();
      setText('command-feedback', response.ok ? `Accepted · firmware ${result.firmware_confirmed ? 'ACK' : 'not acknowledged'} · event ${result.logging_status || 'queued'} · physical state unverified` : (result.error || 'Command failed'));
      await pollState();
    } catch { setText('command-feedback', 'Command failed · backend unavailable'); }
  };
  const commands = {
    'led-apply': () => ({url:'/api/led', target:'lighting', payload:Object.fromEntries(['r','g','b','w'].map(key => [key, Number(byId('led-' + key).value)]))}),
    'led-off': () => ({url:'/api/led', target:'lighting', payload:{r:0,g:0,b:0,w:0}}),
    'fan-on': () => ({url:'/api/fan', target:'fan', payload:{state:'on'}}),
    'fan-off': () => ({url:'/api/fan', target:'fan', payload:{state:'off'}}),
    'fan-speed': () => ({url:'/api/fan/speed', target:'fan', payload:{speed:Number(byId('fan-speed').value)}}),
    'pump-on': () => ({url:'/api/pump', target:'pump', payload:{state:'on'}}),
    'pump-off': () => ({url:'/api/pump', target:'pump', payload:{state:'off'}}),
    'pump-5s': () => ({url:'/api/pump', target:'pump', payload:{state:'5s'}}),
  };
  document.querySelectorAll('[data-command]').forEach(button => button.onclick = async () => {
    pending = null;
    const next = commands[button.dataset.command]();
    const command = next.url === '/api/led' ? 'LED:' + ['r','g','b','w'].map(k => next.payload[k]).join(',') :
      next.url === '/api/fan/speed' ? 'FAN_SPEED:' + next.payload.speed :
      next.url === '/api/fan' ? (next.payload.state === 'on' ? 'FAN_ON' : 'FAN_OFF') :
      ({on:'PUMP_ON', off:'PUMP_OFF', '5s':'PUMP_5S'})[next.payload.state];
    try {
      const response = await fetch('/api/confirmations', {method:'POST', headers:{'Content-Type':'application/json','X-GERM-Token':controlToken},
        body:JSON.stringify({action:'command', payload:{command}})});
      const prepared = await response.json();
      if (!response.ok) throw Error(prepared.error || 'Command inhibited');
      next.payload.expected_state_revision = prepared.state_revision;
      if (prepared.confirmation_id) next.payload.confirmation_id = prepared.confirmation_id;
      pending = next;
      setText('confirm-message', 'Send command to ' + next.target + '? State changes revoke this confirmation. Firmware acknowledgement is not physical verification.');
      dialog.showModal();
    } catch (error) { setText('command-feedback', error.message); }
  });
}

if (page === 'plant') {
  byId('capture-button').onclick = async () => {
    if(captureBusy)return;captureBusy=true;
    lastCaptureFailed=false;
    byId('analyze-button').disabled=true;
    const button = byId('capture-button'); button.disabled = true;
    setText('capture-status', 'Saving camera image…');
    try {
      const plant=byId('capture-plant').value;
      const payload={request_id:crypto.randomUUID(),plant_id:plant ? Number(plant) : null};
      const response = await fetch('/api/camera/capture', {method:'POST', headers:{'X-GERM-Token':controlToken,'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Capture failed');
      setText('capture-status', data.image.indexed ? 'JPEG finalized · SQL metadata committed · trace '+(data.event_status || 'unknown') : 'Saved locally · SQL metadata not acknowledged');
      renderSavedCapture(data.image);
      await pollState();
    } catch (error) { lastCaptureFailed=true;setText('capture-status', error.message); }
    captureBusy=false;await pollState();
  };
  fetch('/api/captures').then(response => response.json()).then(data => {
    renderSavedCapture(data.latest_manual);
    const recent = byId('recent-captures');
    if (data.state !== 'ready') { recent.textContent = 'Awaiting database service'; return; }
    if (!data.recent.length) { recent.textContent = 'No indexed captures'; return; }
    recent.replaceChildren();
    for (const image of data.recent.slice(0, 3)) {
      const link = document.createElement('a');
      link.href = '/captures/' + image.file_path;
      link.textContent = new Date(image.timestamp_utc).toLocaleString();
      recent.append(link);
    }
  }).catch(() => setText('recent-captures', 'Capture history unavailable'));
  byId('analyze-button').onclick=async()=>{
    const image=latestMedia?.recent?.[0];if(!image)return;
    mediaBusy=true;byId('analyze-button').disabled=true;setText('analysis-status','Inference requested · no result committed yet');
    try {
      const response=await fetch('/api/ml/analyze',{method:'POST',headers:{'Content-Type':'application/json','X-GERM-Token':controlToken},body:JSON.stringify({image_id:image.image_id,request_id:crypto.randomUUID()})});
      const result=await response.json();
      if(!response.ok)throw Error(result.error || result.state || 'Inference unavailable');
      analysisRequestId=result.request_id;
      setText('analysis-status','Inference record committed · trace '+(result.event_status || 'pending')+' · synthetic result is not a plant diagnosis');
    } catch(error) {setText('analysis-status',error.message+' · no successful inference acknowledged');}
    finally {mediaBusy=false;await pollState();}
  };
  byId('capture-schedule-form').onsubmit=async event=>{
    event.preventDefault();
    try {
      const response=await fetch('/api/camera/schedule',{method:'POST',headers:{'Content-Type':'application/json','X-GERM-Token':controlToken},body:JSON.stringify({enabled:byId('capture-schedule-enabled').checked,interval_s:Number(byId('capture-interval').value),anchor_utc:byId('capture-anchor').value})});
      const result=await response.json();if(!response.ok)throw Error(result.error || 'Schedule write failed');
      setText('media-schedule-status','Schedule committed · no catch-up burst · trace queued separately');
    } catch(error) {setText('media-schedule-status',error.message);}
  };
  byId('recover-captures').onclick=async()=>{
    try {
      const response=await fetch('/api/media/recover',{method:'POST',headers:{'Content-Type':'application/json','X-GERM-Token':controlToken},body:'{}'});
      const result=await response.json();if(!response.ok)throw Error(result.error || 'Recovery failed');
      setText('media-schedule-status',`Recovery: ${result.indexed.length} indexed · ${result.needs_review.length} need review · ${result.orphaned_files.length} unowned files preserved`);
      await pollState();
    } catch(error) {setText('media-schedule-status',error.message);}
  };
  byId('recover-camera-clock').onclick=async()=>{
    if(!confirm('Acknowledge the camera clock fault? UTC must have recovered. Captures stay inhibited until a strictly later slot; existing claims are retained.'))return;
    try {
      const response=await fetch('/api/media/recover',{method:'POST',headers:{'Content-Type':'application/json','X-GERM-Token':controlToken},body:JSON.stringify({recover_clock:true})});
      const result=await response.json();if(!response.ok)throw Error(result.error || 'Clock recovery failed');
      setText('media-schedule-status','Clock recovery committed · no capture started · resume boundary '+result.clock.resume_not_before_utc);
    } catch(error) {setText('media-schedule-status',error.message);}
    finally {await pollState();}
  };
}

function renderSavedCapture(image) {
  const container=byId('latest-capture');if(!container)return;
  const key=image ? `${image.image_id}:${image.file_path}:${image.file_state || 'unknown'}` : 'none';
  if(displayedImageKey===key)return;displayedImageKey=key;container.replaceChildren();
  if(!image){container.textContent='No indexed image available';return;}
  const detail=document.createElement('small');
  detail.textContent=`${image.source==='synthetic' ? 'SYNTHETIC · ' : ''}${image.timestamp_utc} · ${image.width_px}×${image.height_px} · ${image.size_bytes} bytes · SHA-256 ${image.sha256} · plant ${image.plant_id ?? 'unassigned'}`;
  const link=document.createElement('a');link.href=image.url || '/captures/'+image.file_path;link.textContent='Open saved JPEG';
  container.append(detail,link);
  if(image.file_state==='unavailable_or_corrupt'){container.append('Indexed file unavailable or corrupt');return;}
  const preview=document.createElement('img');preview.className='capture-thumb';preview.src=link.href;preview.alt=image.source==='synthetic' ? 'Saved synthetic test frame' : 'Saved frame';
  preview.onerror=()=>{preview.hidden=true;detail.textContent+=' · image file unavailable or corrupt';};
  container.append(preview);
}

function renderMedia(media,enabled) {
  latestMedia=media;
  if(page!=='plant')return;
  const available=!!media?.camera;
  const camera=media?.camera;
  setText('camera-metadata',available ? `${camera.source} · ${camera.state} · ${camera.timestamp_utc || 'no sample timestamp'} · age ${camera.age_seconds ?? 'unknown'} s` : 'Camera runtime not configured');
  const model=media?.ml?.model;
  setText('model-status',model ? `SYNTHETIC CONTRACT ONLY · ${media.ml.state} · ${model.version} · artifact SHA-256 ${model.artifact_sha256} · ${model.classification_review}` : 'No model configured · '+(media?.ml?.state || 'not_configured')+' · '+(media?.ml?.error || 'no validated plant inference available'));
  byId('capture-button').disabled=captureBusy || !enabled || camera?.state!=='ready' || !media?.experiment_id;
  byId('analyze-button').disabled=captureBusy || mediaBusy || !enabled || !model || !media?.recent?.length || media.recent[0].file_state!=='available';
  byId('save-capture-schedule').disabled=!enabled || !available;
  byId('recover-captures').disabled=!enabled || !available;
  const scheduling=media?.scheduling;
  byId('recover-camera-clock').disabled=!enabled || !available || !scheduling?.operator_recovery_required;
  setText('capture-clock-status',scheduling ? `Scheduler: ${scheduling.state} · ${scheduling.inhibited ? 'INHIBITED' : 'eligible slots only'} · high-water ${scheduling.high_water_utc || 'not observed'} · resume ${scheduling.resume_not_before_utc || 'not set'}${scheduling.operator_recovery_required ? ' · explicit clock acknowledgement required' : ''}` : 'Scheduling state not configured');
  if(!available)return;
  renderSavedCapture(media.recent?.[0]);
  const latest=media.recent?.[0];
  if(latest && !captureBusy && !lastCaptureFailed) setText('capture-status','Last indexed JPEG · SQL metadata committed · trace '+latest.event_status);
  const inferred=media.ml?.latest_result;
  if(inferred && !mediaBusy && inferred.request_id===analysisRequestId) setText('analysis-status','Inference record committed · trace '+inferred.event_status+' · synthetic result is not a plant diagnosis');
  setText('saved-image-age',latest ? `Saved image age ${latest.age_seconds ?? 'unknown (clock mismatch)'} s · trace ${latest.event_status}` : 'No image timestamp');
  const select=byId('capture-plant'),selected=select.value;
  if(select.dataset.experiment!==String(media.experiment_id) || select.options.length!==(media.plants?.length || 0)+1) {
    select.replaceChildren(new Option('Experiment only / plant unassigned',''));
    for(const plant of media.plants || [])select.append(new Option(`Position ${plant.position} · ${plant.species}`,plant.plant_id));
    select.value=selected;select.dataset.experiment=String(media.experiment_id);
  }
  if(!mediaFormInitialized) {
    mediaFormInitialized=true;byId('capture-anchor').value=media.schedule?.anchor_utc || media.server_time_utc;
    byId('capture-interval').value=media.schedule?.interval_s || 3600;
    byId('capture-schedule-enabled').checked=!!media.schedule?.enabled;
  }
}

if (page === 'trends') {
  function drawTrend(box, points) {
    box.className = 'trend-chart'; box.replaceChildren();
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 600 250'); svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Sensor values over time; gaps mean missing or invalid data');
    const valid = points.filter(p => p.value !== null && Number.isFinite(Number(p.value)) && p.quality_flag !== 'invalid');
    if (!valid.length) { box.textContent = 'No valid sensor values in this range.'; return; }
    const values = valid.map(p => Number(p.value));
    const minimum = Math.min(...values), maximum = Math.max(...values);
    const span = Math.max(1, maximum - minimum);
    const times = points.map(p => Date.parse(p.timestamp_utc));
    const first = Math.min(...times), last = Math.max(...times);
    const x = i => 38 + 540 * ((times[i] - first) / Math.max(1, last - first));
    const y = value => 216 - 178 * ((Number(value) - minimum) / span);
    function shape(tag, attributes) {
      const node = document.createElementNS(svgNS, tag);
      for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
      svg.append(node); return node;
    }
    for (let i = 0; i < 4; i++) shape('line', {x1:38, x2:578, y1:38+i*59, y2:38+i*59, stroke:'#355063'});
    let segment = [];
    function flush() {
      if (segment.length > 1) shape('polyline', {points:segment.join(' '), fill:'none', stroke:'#47d77d', 'stroke-width':3});
      segment = [];
    }
    points.forEach((point, i) => {
      const good = point.value !== null && point.quality_flag === 'good' && Number.isFinite(Number(point.value));
      if (good) {
        segment.push(`${x(i)},${y(point.value)}`);
        shape('circle', {cx:x(i), cy:y(point.value), r:2.5, fill:'#47d77d'});
      }
      else {
        flush();
        if (Number.isFinite(Number(point.value)) && point.value !== null)
          shape('circle', {cx:x(i), cy:y(point.value), r:5, fill:point.quality_flag === 'stale' ? '#ffc458' : '#ff686c'});
      }
    });
    flush();
    shape('text', {x:39, y:21, fill:'#b9c9d3', 'font-size':13}).textContent = maximum.toFixed(1);
    shape('text', {x:39, y:239, fill:'#b9c9d3', 'font-size':13}).textContent = minimum.toFixed(1);
    box.append(svg);
    const legend = document.createElement('small');
    legend.textContent = 'Green: valid · Amber: stale · Red: suspect · Gap: missing/invalid';
    box.append(legend);
  }
  const load = async () => {
    const sensor = byId('trend-sensor').value;
    const hours = Number(byId('trend-range').value);
    const start = new Date(Date.now() - hours * 3600000).toISOString();
    const params = new URLSearchParams({sensor, start, end:new Date().toISOString()});
    if (byId('experiment-filter').value) params.set('experiment_id', byId('experiment-filter').value);
    try {
      const data = await (await fetch('/api/trends?' + params)).json();
      const box = byId('trend-content');
      if (data.state !== 'ready') { box.textContent = 'Awaiting database service. No historical values are shown.'; return; }
      if (!data.points.length) { box.textContent = 'No recorded values in this range.'; return; }
      drawTrend(box, data.points.slice(-500));
    } catch { setText('trend-content', 'History service unavailable'); }
  };
  byId('trend-sensor').onchange = load; byId('trend-range').onchange = load;
  byId('experiment-filter').onchange = load; load();
  fetch('/api/experiments').then(r => r.json()).then(data => {
    if (data.state !== 'ready') return;
    for (const experiment of data.items) {
      const option = document.createElement('option'); option.value = experiment.experiment_id;
      option.textContent = experiment.name; byId('experiment-filter').append(option);
    }
  }).catch(() => {});
}

if (page === 'alerts') {
  fetch('/api/alerts').then(r => r.json()).then(data => {
    if (data.state !== 'ready') return;
    const active = byId('active-alerts'); active.className = 'alert-list';
    let offset = 0;
    function showActive() {
      active.replaceChildren();
      if (!data.active.length) { active.textContent = 'No active alerts recorded'; return; }
      for (const item of data.active.slice(offset, offset + 2)) {
        const card = document.createElement('div'); card.className = 'alert-item';
        const title = document.createElement('strong');
        title.textContent = `${item.severity.toUpperCase()} · ${item.source_type}`;
        const message = document.createElement('span'); message.textContent = item.message;
        const detail = document.createElement('small');
        detail.textContent = `${new Date(item.timestamp_utc).toLocaleString()} · ${item.ack_time_utc ? 'Acknowledged' : 'Not acknowledged'}`;
        card.append(title, message, detail);
        if (item.recommended_action) {
          const action = document.createElement('small');
          action.textContent = 'Action: ' + item.recommended_action; card.append(action);
        }
        if (!item.ack_time_utc) {
          const ack = document.createElement('button'); ack.textContent = 'Acknowledge';
          ack.onclick = async () => {
            if (!confirm('Acknowledge this alert? This does not clear the condition.')) return;
            const response = await fetch(`/api/alerts/${item.alert_id}/ack`, {method:'POST', headers:{'X-GERM-Token':controlToken}});
            if (response.ok) location.reload(); else ack.textContent = 'Unavailable';
          };
          card.append(ack);
        }
        active.append(card);
      }
      if (data.active.length > 2) {
        const pager = document.createElement('div'); pager.className = 'alert-pager';
        const previous = document.createElement('button'); previous.textContent = 'Previous';
        previous.disabled = offset === 0; previous.onclick = () => { offset -= 2; showActive(); };
        const next = document.createElement('button'); next.textContent = 'Next';
        next.disabled = offset + 2 >= data.active.length;
        next.onclick = () => { offset += 2; showActive(); };
        pager.append(previous, next); active.append(pager);
      }
    }
    showActive();
    const history = data.history[0];
    setText('alert-history', history ?
      `${data.history.length} records · Latest: ${history.severity} · ${history.message}` :
      'No historical alerts recorded');
  }).catch(() => setText('active-alerts', 'Alert service unavailable'));
}


document.querySelectorAll('[data-workflow]').forEach(button => button.onclick = async () => {
  button.disabled = true;
  const action = button.dataset.workflow;
  const payload = action === 'safe_manual_test' ? {command:'PUMP_5S'} : {};
  const headers = {'Content-Type':'application/json', 'X-GERM-Token':controlToken};
  try {
    const preparedResponse = await fetch('/api/confirmations', {method:'POST', headers, body:JSON.stringify({action, payload})});
    const prepared = await preparedResponse.json();
    if (!preparedResponse.ok) throw Error(prepared.error || 'Workflow inhibited');
    if (prepared.confirmation_id && !confirm(prepared.description + '\nState changes revoke this confirmation. Physical outcomes remain unverified.')) return;
    const response = await fetch('/api/workflow', {method:'POST', headers,
      body:JSON.stringify({action, payload, confirmation_id:prepared.confirmation_id, expected_state_revision:prepared.state_revision})});
    const result = await response.json();
    if (!response.ok) throw Error(result.error || result.reason_codes?.join(', ') || 'Workflow failed');
    setText('command-feedback', 'Workflow accepted · trace event queued until committed · physical state unverified');
  } catch (error) { setText('command-feedback', error.message); }
  finally { await pollState(); }
});

function renderGrow(grow,enabled,logging) {
  latestGrow=grow;
  const ready=grow?.state === 'ready';
  const cycle=grow?.cycle;
  setText('grow-summary',ready ? cycle ? `${cycle.profile_id} · ${cycle.status} · schedules ${grow.schedules_armed ? 'armed for simulation' : 'inhibited'}` : 'Select Basil or Spearmint in Settings' : 'Grow repository ' + (grow?.state || 'unavailable'));
  setText('logging-summary',`Events: ${logging?.state || 'not configured'} · pending ${logging?.pending ?? 'unknown'} · dropped ${logging?.dropped ?? 'unknown'} · last command ${grow?.last_command_event || 'unknown'}`);
  setText('home-grow-day',grow?.grow_day ? `Grow day ${grow.grow_day} (24-hour periods since first start)` : 'Grow day unavailable · cycle not started');
  const definitions=grow?.schedules?.map(s=>s.definition) || [];
  const light=definitions.find(d=>d.target==='lighting' && d.enabled);
  const pump=definitions.find(d=>d.target==='pump' && d.enabled);
  setText('home-light-schedule', light ? `Light: ${light.start_utc}–${light.end_utc} UTC · RGB ${light.rgb.join(',')} · host settings` : 'Light schedule unconfigured or disabled');
  setText('home-mist-schedule',pump ? `Mist: 5 s pulse every ${pump.interval_s} s · host settings` : 'Mist schedule unconfigured or disabled');
  setText('last-maintenance',ready ? grow.last_maintenance ? `Last maintenance activity: ${grow.last_maintenance.action} · ${grow.last_maintenance.timestamp_utc}` : 'No maintenance activity recorded' : 'Last maintenance unavailable');
  document.querySelectorAll('.grow-only').forEach(button=>{button.hidden=!cycle || cycle.status==='complete';});
  if (page!=='settings')return;
  setText('settings-experiment',cycle ? `${cycle.profile_id} · ${cycle.status} · ${grow.grow_day ? 'day '+grow.grow_day : 'not started'}` : 'No active grow cycle');
  setText('profile-notice',grow?.configuration_notice || 'Basil and Spearmint await configured host repository');
  const select=byId('grow-profile');
  if (ready && !select.options.length)for (const p of grow.profiles) {const option=document.createElement('option');option.value=p.profile_id;option.textContent=p.name+' · timings unapproved';select.append(option);}
  select.disabled=!enabled || !ready || (cycle && cycle.status!=='complete');
  if (cycle && cycle.status!=='complete') select.value=cycle.profile_id;
  if (cycle && scheduleEditorCycle!==cycle.cycle_id) {
    scheduleEditorCycle=cycle.cycle_id;
    byId('light-enabled').checked=!!light;byId('mist-enabled').checked=!!pump;
    byId('schedule-rgb').value=light ? light.rgb.join(',') : '0,0,0';
    if (light) {byId('light-start').value=light.start_utc;byId('light-end').value=light.end_utc;}
    if (pump) byId('mist-interval').value=pump.interval_s;
  }
  byId('create-cycle').disabled=select.disabled;
  byId('save-schedules').disabled=!enabled || !ready || cycle?.status!=='paused';
  byId('recover-grow').disabled=!enabled;
}

if (page==='settings') {
  async function growPost(url,body) {
    const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-GERM-Token':controlToken},body:JSON.stringify(body)});
    const data=await response.json();
    if (!response.ok)throw Error(data.error || 'Grow operation rejected');
    setText('grow-form-status','Configuration committed · trace events may still be queued · schedules remain inhibited until confirmed Start');
    await pollState();
  }
  byId('profile-form').onsubmit=async event=>{
    event.preventDefault();byId('create-cycle').disabled=true;
    try {await growPost('/api/grow/cycles',{profile_id:byId('grow-profile').value,name:byId('grow-name').value});}
    catch (error) {setText('grow-form-status',error.message);await pollState();}
  };
  byId('schedule-form').onsubmit=async event=>{
    event.preventDefault();byId('save-schedules').disabled=true;
    const schedules=[];
    if (byId('light-enabled').checked)schedules.push({target:'lighting',enabled:true,start_utc:byId('light-start').value,end_utc:byId('light-end').value,rgb:byId('schedule-rgb').value.split(',').map(Number)});
    if (byId('mist-enabled').checked)schedules.push({target:'pump',enabled:true,interval_s:Number(byId('mist-interval').value)});
    try {await growPost('/api/grow/schedules',{schedules});}
    catch (error) {setText('grow-form-status',error.message);await pollState();}
  };
  byId('recover-grow').onclick=async()=>{try {await growPost('/api/grow/recover',{});}catch(error){setText('grow-form-status',error.message);}};
}
