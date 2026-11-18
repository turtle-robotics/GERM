/* Local-only HMI. Every hardware, SQL, and ML request goes through Flask. */
const page = document.body.dataset.page;
const byId = id => document.getElementById(id);
const setText = (id, text) => { const node = byId(id); if (node) node.textContent = text; };
let latestState = null;

function clock() {
  setText('clock', new Intl.DateTimeFormat(undefined, {hour:'numeric', minute:'2-digit'}).format(new Date()));
}
clock(); setInterval(clock, 30000);

const camera = byId('camera-image');
if (camera) {
  const refresh = () => { camera.src = '/camera.jpg?t=' + Date.now(); };
  camera.onload = () => { byId('camera-status').hidden = true; setTimeout(refresh, 200); };
  camera.onerror = () => { byId('camera-status').hidden = false; setTimeout(refresh, 1200); };
  refresh();
}

function sensorText(reading) {
  if (!reading || reading.state === 'unavailable') return ['NO DATA', 'Unavailable'];
  const value = Number.isInteger(reading.value) ? reading.value : Number(reading.value).toFixed(1);
  const unit = reading.unit === '%RH' ? '%' : reading.unit;
  if (reading.state === 'stale') return [`${value} ${unit}`, `STALE · ${reading.age_seconds}s old`];
  return [`${value} ${unit}`, `LIVE · ${reading.source}`];
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
    };
    const [title, detail] = labels[state] || ['No ML result yet','Waiting for first analysis'];
    setText('ml-class', title);
    setText('ml-detail', detail);
    return;
  }
  const low = result.review_required || result.predicted_class === 'uncertain';
  setText('ml-class', low ? 'Review Required' : result.predicted_class);
  const confidence = typeof result.confidence === 'number' ?
    `${Math.round(result.confidence * 100)}%` : 'confidence unavailable';
  setText('ml-detail', `${confidence} · ${result.model_version || 'model unknown'} · ${result.timestamp_utc || 'time unavailable'}`);
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
  const state = byId('system-state');
  state.textContent = data.system_state;
  state.className = 'state-pill ' + data.system_state.toLowerCase();
  setText('arduino-head', 'Arduino: ' + data.arduino.state);
  for (const name of ['air_temperature','humidity','water_temperature']) renderSensor(name, data.sensors[name]);
  renderML(data.ml);
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
    const offline = data.arduino.state !== 'connected';
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
    for (const name of ['air_temperature','humidity','water_temperature']) {
      setText(name + '-value', 'NO DATA'); setText(name + '-state', 'Backend unavailable');
    }
    setText('alert-count', 'Count unknown');
    setText('ml-class', 'ML status unavailable');
    setText('ml-detail', 'Backend unavailable');
    for (const name of ['lighting','fan','pump']) {
      setText(name + '-status', 'Backend unavailable');
      setText(name + '-detail', 'Backend unavailable');
    }
    document.querySelectorAll('[data-command]').forEach(button => button.disabled = true);
  }
}
pollState(); setInterval(pollState, 2000);

if (page === 'controls') {
  let uploading = false;
  byId('lighting-upload').onclick = async () => {
    if (uploading) return;
    uploading = true;
    const button = byId('lighting-upload');
    button.disabled = true;
    const mode = byId('lighting-mode');
    mode.disabled = true;
    const body = new FormData(); body.append('mode', mode.value);
    setText('lighting-upload-status', 'Compiling and uploading… outputs turn off');
    try {
      const response = await fetch('/api/firmware', {method:'POST', headers:{'X-GERM-Token':firmwareToken}, body});
      const result = await response.json();
      if (!response.ok) throw Error(result.error || 'Upload failed');
      setText('lighting-upload-status', result.warning || 'Uploaded · selected mode confirmed');
    } catch (error) { setText('lighting-upload-status', error.message); }
    finally { uploading = false; button.disabled = false; mode.disabled = false; await pollState(); }
  };
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
      const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
      const result = await response.json();
      setText(target + '-detail', response.ok ? 'Firmware confirmed output setting' : (result.error || 'Command failed'));
      await pollState();
    } catch { setText(target + '-detail', 'Command failed · backend unavailable'); }
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
  document.querySelectorAll('[data-command]').forEach(button => button.onclick = () => {
    pending = commands[button.dataset.command]();
    setText('confirm-message', `Send ${button.textContent.trim()} to ${pending.target}? Firmware reports output settings; physical operation and E-STOP state are not measured.`);
    dialog.showModal();
  });
}

if (page === 'plant') {
  byId('capture-button').onclick = async () => {
    const button = byId('capture-button'); button.disabled = true;
    setText('capture-status', 'Saving camera image…');
    try {
      const response = await fetch('/api/camera/capture', {method:'POST'});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Capture failed');
      setText('capture-status', data.image.indexed ? 'Saved and indexed in SQL' : 'Saved locally · awaiting SQL image index');
      renderCapture(data.image);
    } catch (error) { setText('capture-status', error.message); }
    button.disabled = false;
  };
  function renderCapture(image) {
    const container = byId('latest-capture'); container.replaceChildren();
    if (!image) { container.textContent = 'No manual capture this session'; return; }
    const preview = document.createElement('img');
    preview.className = 'capture-thumb'; preview.src = image.url;
    preview.alt = 'Latest saved GERM image';
    const link = document.createElement('a'); link.href = image.url;
    link.textContent = 'View saved JPEG · ' + new Date(image.timestamp_utc).toLocaleTimeString();
    container.append(preview, link);
  }
  fetch('/api/captures').then(response => response.json()).then(data => {
    renderCapture(data.latest_manual);
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
            const response = await fetch(`/api/alerts/${item.alert_id}/ack`, {method:'POST'});
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
