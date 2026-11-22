(() => {
  const BASE = localStorage.getItem('disastra-api-base') || (location.protocol.startsWith('http') ? location.origin : 'http://localhost:8000');
  const DEVICE = localStorage.getItem('disastra-device-id') || crypto.randomUUID();
  localStorage.setItem('disastra-device-id', DEVICE);
  const key = 'disastra-pending-v2';
  let pending = JSON.parse(localStorage.getItem(key) || '[]');
  let zones = null, facilities = [], vehicles = [], roadReports = [], selected = null;
  let selectedPoint = null, selectedAccuracy = null, selectedFacility = null, routeLayers = [], map = null, citizenMap = null;
  let zonesLayer, sosLayer, facilitiesLayer, roadsLayer, vehiclesLayer, routesLayer, zoneRenderer;
  let loadLock = false, useDemoSource = false;
  const center = [20.5937, 78.9629]; // India overview; no victim location is implied.
  const $ = id => document.getElementById(id);
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const apiBase = () => ($('apiBase')?.value || BASE).trim().replace(/\/+$/, '');
  const savePending = () => localStorage.setItem(key, JSON.stringify(pending));
  const headers = extra => ({'Content-Type':'application/json','X-User-Role':'control_room',...extra});
  async function api(path, opts = {}) {
    const response = await fetch(`${apiBase()}${path}`, {...opts,headers:headers(opts.headers)});
    if (!response.ok) {
      let detail; try { detail = await response.json(); } catch {}
      throw new Error(detail?.detail?.error?.message || detail?.error?.message || `${response.status} ${response.statusText}`);
    }
    return response.status === 204 ? null : response.json();
  }
  function toast(message) { const el = $('toast'); if (!el) return; el.textContent = message; el.classList.add('show'); setTimeout(() => el.classList.remove('show'), 3200); }
  function labelNeed(value) { const v = String(value || 'OTHER').toUpperCase(); return ({MED:'Medical',MEDICAL:'Medical',FOOD:'Food / water',WATER:'Food / water',MEDICINES:'Medicines',EVAC:'Evacuation',EVACUATION:'Evacuation',TRAP:'Trapped',OTHER:'Other'})[v] || v.toLowerCase().replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase()); }
  function normalize(row) {
    const created = row.created_at ? new Date(row.created_at) : new Date();
    return {...row,id:String(row.id||row.client_msg_id),level:String(row.severity || row.level || 'yellow').toLowerCase(),need:labelNeed(row.need_type || row.need),where:row.lat != null && row.lon != null ? `${Number(row.lat).toFixed(3)}, ${Number(row.lon).toFixed(3)}` : 'Location withheld',people:Number(row.people_count || row.people || 1),score:Number(row.priority_score || row.score || 0),wait:Math.max(0,Math.floor((Date.now()-created.getTime())/60000)),status:String(row.status || 'pending'),lat:row.lat,lon:row.lon,created_at:row.created_at};
  }
  function allRequests() {
    const fromApi = Array.isArray(window.disastraRequests) ? window.disastraRequests : [];
    const ids = new Set(fromApi.map(x => x.client_msg_id));
    return [...fromApi.map(normalize), ...pending.filter(p => !ids.has(p.client_msg_id)).map(normalize)];
  }
  function markerIcon(level) {
    const isRed = level === 'red';
    const bg = isRed ? '#ff2255' : '#ffaa00';
    const glow = isRed ? 'rgba(255,34,85,0.7)' : 'rgba(255,170,0,0.6)';
    const symbol = isRed ? '!' : '▲';
    return L.divIcon({
      className: '',
      html: `<div style="width:30px;height:30px;border-radius:50%;background:${bg};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:900;font-family:sans-serif;font-size:16px;box-shadow:0 0 16px ${glow};border:2px solid #fff;animation:beacon 1.5s infinite" aria-label="${isRed?'Red SOS critical':'Yellow SOS assist'}">${symbol}</div>`,
      iconSize: [30, 30],
      iconAnchor: [15, 15]
    });
  }
  function initMap(id) {
    if (!window.L || !$(id)) return null;
    const m = L.map(id,{zoomControl:true,scrollWheelZoom:true}).setView(center,5);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(m);
    return m;
  }
  function initMaps() {
    if (!map) {
      map = initMap('liveMap');
      if (map) {
        zoneRenderer=L.svg({padding:.5});map.addLayer(zoneRenderer);zonesLayer=L.geoJSON(null,{renderer:zoneRenderer,style:f=>zoneStyle(f.properties?.zone_type),onEachFeature:(f,l)=>l.bindPopup(`<div class="zone-popup"><b>${escapeHtml(f.properties?.zone_type)} zone</b><br>${escapeHtml(f.properties?.reason || 'Classification reason unavailable')}<br>Source: ${escapeHtml(f.properties?.source || 'Not reported')}<br>Confidence: ${f.properties?.confidence == null?'Not reported':Math.round(f.properties.confidence*100)+'%'}</div>`)}).addTo(map);
        sosLayer=L.layerGroup().addTo(map); facilitiesLayer=L.layerGroup().addTo(map); roadsLayer=L.layerGroup().addTo(map); vehiclesLayer=L.layerGroup().addTo(map); routesLayer=L.layerGroup().addTo(map);
        map.on('click', e=>setLocation(e.latlng.lat,e.latlng.lng,'map'));
      }
    }
    if (!citizenMap) {
      citizenMap=initMap('citizenMap');
      if (citizenMap) citizenMap.on('click',e=>setLocation(e.latlng.lat,e.latlng.lng,'map'));
    }
  }
  function zoneStyle(zone) { return ({red:{color:'#ff554f',weight:2,dashArray:'7 4',fillColor:'url(#disastra-red-hatch)',fillOpacity:.62},yellow:{color:'#ffc35e',weight:2,dashArray:'2 5',fillColor:'url(#disastra-yellow-stripe)',fillOpacity:.62},green:{color:'#43d19e',weight:2,fillColor:'#43d19e',fillOpacity:.16}})[zone] || {color:'#8aa1b4',weight:1,fillOpacity:.08}; }
  function addZonePatterns(){const svg=zoneRenderer?._container;if(!svg||svg.querySelector('#disastra-red-hatch'))return;const ns='http://www.w3.org/2000/svg',defs=document.createElementNS(ns,'defs');for(const [id,color,cross] of [['disastra-red-hatch','#ff625b',true],['disastra-yellow-stripe','#ffc35e',false]]){const p=document.createElementNS(ns,'pattern');p.setAttribute('id',id);p.setAttribute('width','10');p.setAttribute('height','10');p.setAttribute('patternUnits','userSpaceOnUse');const a=document.createElementNS(ns,'path');a.setAttribute('d',cross?'M0 0L10 10M10 0L0 10':'M0 3H10');a.setAttribute('stroke',color);a.setAttribute('stroke-width',cross?'1.4':'2');a.setAttribute('opacity','.78');p.appendChild(a);defs.appendChild(p);}svg.insertBefore(defs,svg.firstChild);}
  function redraw() {
    if (!map) return;
    if (zonesLayer && zones) { zonesLayer.clearLayers(); zonesLayer.addData(zones); }
    sosLayer.clearLayers(); facilitiesLayer.clearLayers(); roadsLayer.clearLayers(); vehiclesLayer.clearLayers();
    const rows=allRequests();
    for (const r of rows) if (Number.isFinite(Number(r.lat)) && Number.isFinite(Number(r.lon))) {
      const marker=L.marker([Number(r.lat),Number(r.lon)],{icon:markerIcon(r.level)}).bindPopup(`<b>${r.level==='red'?'URGENT · Red SOS':'Yellow SOS · NEED HELP'}</b><br>${escapeHtml(r.id)} · ${escapeHtml(r.need)}<br>${r.people} people · priority ${r.score}<br>Status: ${escapeHtml(r.status)}`);
      marker.on('click',()=>selectRequest(r.id)); marker.addTo(sosLayer);
    }
    for (const f of facilities) if (Number.isFinite(Number(f.lat))&&Number.isFinite(Number(f.lon))) L.circleMarker([f.lat,f.lon],{radius:7,color:f.type==='hospital'?'#75d8ff':'#63e1b0',fillOpacity:.9,weight:2}).bindPopup(`<b>${escapeHtml(f.name)}</b><br>${escapeHtml(f.type)} · ${escapeHtml(f.status)}<br>${f.in_red_zone?'Red zone facility — excluded':''}`).addTo(facilitiesLayer);
    for (const r of roadReports) if (Number.isFinite(Number(r.lat))&&Number.isFinite(Number(r.lon))) L.circleMarker([r.lat,r.lon],{radius:6,color:r.status==='blocked'?'#ff645a':'#4cdb9d',fillColor:r.status==='blocked'?'#ff645a':'#4cdb9d',fillOpacity:.85}).bindPopup(`Road ${escapeHtml(r.status)} · ${escapeHtml(r.segment_id || 'reported road')}`).addTo(roadsLayer);
    for (const v of vehicles) if (Number.isFinite(Number(v.lat))&&Number.isFinite(Number(v.lon))) L.circleMarker([v.lat,v.lon],{radius:6,color:'#57caff',fillColor:'#57caff',fillOpacity:.9}).bindPopup(`${escapeHtml(v.type)} · ${escapeHtml(v.provider)} · ${escapeHtml(v.status)}`).addTo(vehiclesLayer);
    if (selectedPoint && window.pickMarker) { window.pickMarker.setLatLng(selectedPoint); }
    for(const group of routeLayers) if(group) group.addTo(routesLayer);
  }
  function setLayer(name,on) {
    if (!map) return;
    const mapGroups={sos:sosLayer,facilities:facilitiesLayer,routes:routesLayer};if(mapGroups[name]){if(on)mapGroups[name].addTo(map);else map.removeLayer(mapGroups[name]);return;}
    if(!zonesLayer)return;
    const hazards=document.querySelector('[data-layer=zones]')?.checked!==false;
    const safe=document.querySelector('[data-layer=safe]')?.checked!==false;
    zonesLayer.eachLayer(layer=>{const zone=layer.feature?.properties?.zone_type,visible=zone==='green'?safe:hazards,base=zoneStyle(zone);layer.setStyle({...base,opacity:visible?1:0,fillOpacity:visible?(base.fillOpacity||0):0});});
  }
  function setLocation(lat,lon,source='map',accuracy=null) {
    selectedPoint=[Number(lat),Number(lon)];selectedAccuracy=source==='geolocation'&&Number.isFinite(Number(accuracy))?Number(accuracy):null;
    if(map){if(!window.pickMarker)window.pickMarker=L.marker(selectedPoint,{draggable:true}).addTo(map);else window.pickMarker.setLatLng(selectedPoint);window.pickMarker.bindPopup('Selected response location').openPopup();window.pickMarker.off('dragend').on('dragend',e=>{const p=e.target.getLatLng();setLocation(p.lat,p.lng,'map')});}
    if(citizenMap){citizenMap.setView(selectedPoint,14);if(!window.citizenPick)window.citizenPick=L.marker(selectedPoint,{draggable:true}).addTo(citizenMap);else window.citizenPick.setLatLng(selectedPoint);window.citizenPick.bindPopup('Selected location').openPopup();window.citizenPick.off('dragend').on('dragend',e=>{const p=e.target.getLatLng();setLocation(p.lat,p.lng,'map')});}
    $('mapCoordinates').textContent=`${Math.abs(lat).toFixed(5)}° ${lat>=0?'N':'S'} · ${Math.abs(lon).toFixed(5)}° ${lon>=0?'E':'W'}`;
    $('citizenLocationState').textContent='LOCATION SELECTED'; $('citizenZone').innerHTML='⌖ &nbsp;Selected location<small>Tap elsewhere on the map to adjust</small>';
    $('regionLabel').textContent='Location selected · backend zone classification pending';
    if(source==='geolocation') toast('Your current location is set on both maps');
    if(source!=='request')loadFacilities(lat,lon); if(map)map.setView(selectedPoint,14); redraw();
  }
  function populateSatellite(data) {
    if(!data?.features?.length){$('satStatus').textContent='No zone records returned';$('satSource').textContent='No source reported';$('satTime').textContent='—';$('satHazard').textContent='—';$('satIntensity').textContent='—';$('satArea').textContent='—';return;}
    const p=data.features[0].properties||{};
    const sources=[...new Set(data.features.map(x=>x.properties?.source).filter(Boolean))];
    const valid=data.features.map(x=>x.properties?.valid_from).filter(Boolean).sort().at(-1);
    $('satStatus').textContent='Backend zone records available';
    $('satSource').textContent=sources.join(' · ')||'Source not provided';
    $('satTime').textContent=valid?new Date(valid).toLocaleString()+' · backend record time':'Timestamp not provided';
    $('satHazard').textContent=[...new Set(data.features.map(x=>x.properties?.hazard_type).filter(Boolean))].join(', ')||'Not reported';
    const conf=data.features.map(x=>Number(x.properties?.confidence)).filter(Number.isFinite); $('satIntensity').textContent=conf.length?`Classification confidence · ${(Math.max(...conf)*100).toFixed(0)}% maximum`:'Confidence not provided';
    const ringArea=ring=>{let sum=0;for(let i=0;i<ring.length-1;i++){const [x1,y1]=ring[i],[x2,y2]=ring[i+1];sum+=(x2-x1)*Math.PI/180*(2+Math.sin(y1*Math.PI/180)+Math.sin(y2*Math.PI/180));}return Math.abs(sum)*6371008.8*6371008.8/2;};const totalArea=data.features.reduce((sum,f)=>sum+(f.geometry?.coordinates||[]).reduce((a,ring)=>a+ringArea(ring),0),0);$('satArea').textContent=totalArea?`${(totalArea/1e6).toFixed(1)} km² · zone polygon sum`:'Geometry unavailable';
    $('regionLabel').textContent=`${data.features.length} zone features · snapshot metadata only`;
  }
  function renderQueue() {
    const lev=$('levelFilter')?.value||'all', need=$('needFilter')?.value||'all';
    const list=allRequests().filter(x=>(lev==='all'||x.level===lev)&&(need==='all'||x.need===need)).sort((a,b)=>a.level===b.level?b.score-a.score||a.wait-b.wait:a.level==='red'?-1:1);
    $('queueCount').textContent=String(list.length);
    $('queue').innerHTML=list.length?list.map(x=>`<article class="qitem ${x.level}" data-request="${escapeHtml(x.id)}"><div class="qicon" aria-label="${x.level==='red'?'Red SOS urgent':'Yellow SOS need help'}">${x.level==='red'?'!':'⚠'}</div><div><div class="qtitle">${x.level==='red'?'Red SOS · URGENT':'Yellow SOS · NEED HELP'} ${x.battery_pct!=null&&x.battery_pct<10?'<span class="freshness-pill">⚑ LOW BATTERY</span>':''}</div><div class="qmeta">${escapeHtml(x.id)} · ${escapeHtml(x.where)} · ${escapeHtml(x.need)} · ${x.people} people · ${x.wait} min</div></div><span class="tag ${x.level==='yellow'?'yellow':''}">${x.level.toUpperCase()}</span><div class="qactions"><button class="btn primary" data-action="dispatch" data-id="${escapeHtml(x.id)}">${x.level==='red'?'One-tap dispatch':'Dispatch request'}</button><button class="btn" data-action="select" data-id="${escapeHtml(x.id)}">View routes</button>${x.level==='yellow'?`<button class="btn redbtn" data-action="upgrade" data-id="${escapeHtml(x.id)}">Upgrade to Red SOS</button>`:''}<button class="btn" data-action="relabel" data-id="${escapeHtml(x.id)}">Re-label</button></div></article>`).join(''):'<div class="empty-state">No requests returned by the backend. New SOS requests will appear here after ingestion.</div>';
  }
  async function loadFacilities(lat,lon) {
    if(!Number.isFinite(Number(lat))||!Number.isFinite(Number(lon)))return;
    $('facilityOrigin').textContent=`${Number(lat).toFixed(3)}, ${Number(lon).toFixed(3)}`;
    try {
      const [safeRows,allRows]=await Promise.all([api(`/v1/facilities/nearest?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&limit=6&exclude_red=true`),api(`/v1/facilities/nearest?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&limit=6&exclude_red=false`)]);
      facilities=[...new Map([...safeRows,...allRows].map(f=>[String(f.id),f])).values()];
      renderFacilities(); redraw();
    } catch(e) { $('facilityList').innerHTML=`<div class="empty-state data-error">Facility lookup unavailable: ${escapeHtml(e.message)}</div>`; }
  }
  function renderFacilities() {
    const safe=facilities.filter(f=>!f.in_red_zone), excluded=facilities.filter(f=>f.in_red_zone);
    $('facilityList').innerHTML=[...safe,...excluded].map(f=>`<div class="data-row"><span>${f.type==='hospital'?'✚':f.type==='shelter'?'⌂':'✦'}</span><span>${escapeHtml(f.name)}<small>${escapeHtml(f.type)} · ${escapeHtml(f.status)}${f.in_red_zone?' · RED ZONE — EXCLUDED':''}</small></span><strong>${f.in_red_zone?'Excluded':f.eta_minutes!=null?`${f.eta_minutes} min`:f.distance_km!=null?`${f.distance_km} km`:''}</strong></div>`).join('')||'<div class="empty-state">The backend returned no nearby facilities for this location.</div>';
    $('citizenFacilities').innerHTML=safe.slice(0,3).map(f=>`<div class="facility">${f.type==='hospital'?'🏥':f.type==='shelter'?'⌂':'✦'} &nbsp;${escapeHtml(f.name)} <small>${escapeHtml(f.status)}</small><b>${f.eta_minutes!=null?`${f.eta_minutes} min`:''}</b></div>`).join('')||'<div class="empty-state">No safe facilities returned for this location.</div>';
    const select=$('destinationSelect'), old=selectedFacility;select.innerHTML='<option value="">Automatic safe facility</option>'+safe.map(f=>`<option value="${f.id}">${escapeHtml(f.name)}${f.eta_minutes!=null?` · ${f.eta_minutes} min`:''}</option>`).join('');
    if(old&&safe.some(f=>String(f.id)===String(old)))select.value=String(old);
  }
  function renderVehicles() {
    $('vehicleCount').textContent=`${vehicles.length} registered`;
    $('vehicleList').innerHTML=vehicles.map(v=>`<div class="data-row"><span>◇</span><span>${escapeHtml(v.provider||v.type)}<small>${escapeHtml(v.type)} · capacity ${v.capacity??'unknown'}</small></span><strong>${escapeHtml(v.status)}</strong></div>`).join('')||'<div class="empty-state">No vehicles are currently listed by the backend.</div>';
    $('vehicleSelect').innerHTML='<option value="">Automatic match</option>'+vehicles.map(v=>`<option value="${v.id}">${escapeHtml(v.type)} · ${escapeHtml(v.provider)} · ${escapeHtml(v.status)}</option>`).join('');
    const count={};for(const v of vehicles)count[v.status]=(count[v.status]||0)+1;
  }
  function renderRoads(){ $('roadList').innerHTML=roadReports.map(r=>`<div class="data-row"><span>${r.status==='blocked'?'⚠':'✓'}</span><span>${escapeHtml(r.segment_id||'Road report')}<small>${escapeHtml(r.reporter||'Volunteer')} · ${r.at?new Date(r.at).toLocaleString():''}</small></span><strong>${escapeHtml(r.status)}</strong></div>`).join('')||'<div class="empty-state">No road reports returned.</div>'; }
  function renderImpact(d) { if(!d)return; $('impactRed').textContent=Number(d.red_population||0).toLocaleString();$('impactYellow').textContent=Number(d.yellow_population||0).toLocaleString();$('impactGreen').textContent=Number(d.green_population||0).toLocaleString(); }
  async function retryPending(){
    for(const p of [...pending])try{const sent=await api('/v1/sos',{method:'POST',body:JSON.stringify(p)});pending=pending.filter(x=>x.client_msg_id!==p.client_msg_id);savePending();p.serverId=sent.id;}catch(e){/* Keep the exact client_msg_id so retry remains idempotent. */}
  }
  async function loadData({quiet=false}={}) {
    if(loadLock)return;loadLock=true;
    try {
      const health=await api('/health'); $('apiStatus').textContent=`API ${health.status==='healthy'?'CONNECTED':'UNAVAILABLE'} · ${health.version||''}`;$('apiStatus').classList.remove('data-error');
      await retryPending();
      const results=await Promise.allSettled([api('/v1/sos?limit=200'),api('/v1/zones?hazard=flood&format=geojson'),api('/v1/population?hazard=flood'),api('/v1/road-report'),api('/v1/dispatch/vehicles')]);
      const [sosR,zoneR,popR,roadsR,vehiclesR]=results;
      if(sosR.status!=='fulfilled')throw sosR.reason;
      const sos=sosR.value;window.disastraRequests=sos;renderQueue();
      if(zoneR.status==='fulfilled'){const zoneData=zoneR.value;zones=zoneData;populateSatellite(zoneData);if(map){zonesLayer.clearLayers();zonesLayer.addData(zoneData);addZonePatterns();setLayer('zones',true);if(zoneData.features?.length){const bounds=zonesLayer.getBounds();if(bounds.isValid()&&!selectedPoint)map.fitBounds(bounds.pad(.13));}}}
      else{$('satStatus').textContent='Zone endpoint unavailable';$('satSource').textContent='No data loaded';$('satArea').textContent='—';}
      if(popR.status==='fulfilled')renderImpact(popR.value);else{$('impactRed').textContent='—';$('impactYellow').textContent='—';$('impactGreen').textContent='—';}
      roadReports=roadsR.status==='fulfilled'?roadsR.value:[];vehicles=vehiclesR.status==='fulfilled'?vehiclesR.value:[];
      renderVehicles();renderRoads();redraw();$('updatedAt').textContent=`API refreshed ${new Date().toLocaleTimeString()}`;
      if(!quiet)toast(`Backend connected · ${sos.length} SOS · ${zoneR.status==='fulfilled'?zoneR.value.features?.length||0:0} zone features`);
      if(selected){const again=sos.find(x=>String(x.id)===String(selected.id));if(again){selected=normalize(again);updateStatus(selected);}}
    } catch(e) {
      $('apiStatus').textContent='API DISCONNECTED';$('apiStatus').classList.add('data-error');$('updatedAt').textContent='No live backend connection';
      $('satStatus').textContent='Backend unavailable · no live observation';$('satSource').textContent='No source loaded';$('satArea').textContent='—';
      window.disastraRequests=[];renderQueue(); if(!quiet)toast(`Backend unavailable: ${e.message}`);
    } finally {loadLock=false;}
  }
  function updateStatus(x) {
    if(!x)return;
    $('statusLead').textContent=`${x.level==='red'?'Red SOS · URGENT':'Yellow SOS · NEED HELP'} · ${x.id} · ${x.status}`;
    $('upgradeBtn').style.display=x.level==='yellow'?'block':'none';
    $('step-status-placeholder');
    const steps=document.querySelectorAll('.steps .step');
    const s=String(x.status).toLowerCase();const stage=['received','acknowledged','in_progress','closed'].includes(s)?2:s==='relayed'?1:0;
    steps.forEach((el,i)=>{el.classList.toggle('done',i<stage||i===0&&stage===0);el.classList.toggle('current',i===stage);el.querySelector('.dot').textContent=i<stage||i===0?'✓':'·'});
  }
  async function locate() {
    if(!navigator.geolocation){toast('Location is not available in this browser. Tap your location on the map.');return;}
    navigator.geolocation.getCurrentPosition(pos=>setLocation(pos.coords.latitude,pos.coords.longitude,'geolocation',pos.coords.accuracy),err=>toast(err.code===1?'Location permission was declined. Tap your location on the map.':'Could not get your location. Tap your location on the map.'),{enableHighAccuracy:true,timeout:12000,maximumAge:30000});
  }
  async function createSOS(level,need='OTHER',people=1) {
    if(!selectedPoint){toast('Select your location on the map before sending an SOS');$('citizenMap').scrollIntoView({behavior:'smooth',block:'center'});return null;}
    const lat=selectedPoint[0],lon=selectedPoint[1], id=crypto.randomUUID();
    const code=({Medical:'MED','Minor medical':'MED','Food / water':'FOOD',Medicines:'MED','Evacuation help':'EVAC',Evacuation:'EVAC',Water:'FOOD',Other:'OTHER'})[need]||String(need).toUpperCase();
    const payload={client_msg_id:id,device_id:DEVICE,lat,lon,accuracy_m:selectedAccuracy,severity:level,need_type:code,people_count:Number(people)||1,battery_pct:null,channel:({ 'SMS only':'sms','Nearby phone mesh only':'mesh','Offline queue (retry later)':'mesh'})[$('channel')?.value]||'internet',created_at:new Date().toISOString()};
    const local={...payload,id,level,need:labelNeed(code),people:payload.people_count,status:'queued',where:`${lat.toFixed(3)}, ${lon.toFixed(3)}`,priority_score:level==='red'?100:40,wait:0};
    pending.push(payload);savePending();items=[local,...items];window.disastraRequests=allRequests();activeSOS=local;selected=local;updateStatus(local);renderQueue();redraw();toast(`${level==='red'?'Red alert':'Yellow request'} saved locally · Queued`);
    try{const created=await api('/v1/sos',{method:'POST',body:JSON.stringify(payload)});pending=pending.filter(p=>p.client_msg_id!==id);savePending();window.disastraRequests=[created,...(window.disastraRequests||[]).filter(x=>x.id!==created.id)];selected=normalize(created);activeSOS=selected;updateStatus(selected);renderQueue();redraw();toast(`${level==='red'?'Red alert':'Yellow request'} received by control room`);loadFacilities(lat,lon);}catch(e){toast(`Saved and queued on this device. Backend will retry: ${e.message}`);}
    return local;
  }
  async function upgrade(id) {
    if(!rawIsBackend(id)){toast('This SOS is still queued on this device and will sync before it can be upgraded.');return;}
    const x=allRequests().find(r=>String(r.id)===String(id));if(!x)return;
    try{const result=await api(`/v1/sos/${encodeURIComponent(id)}/severity`,{method:'PATCH',body:JSON.stringify({severity:'red',actor:'control_room',reason:'Operator reviewed and upgraded urgent request'})});
      window.disastraRequests=(window.disastraRequests||[]).map(r=>String(r.id)===String(id)?result:r);selected=normalize(result);activeSOS=selected;savePending();renderQueue();updateStatus(selected);redraw();toast('Yellow SOS upgraded to Red in backend queue');}
    catch(e){toast(`Upgrade failed: ${e.message}`);}
  }
  async function relabel(id) {
    if(!rawIsBackend(id)){toast('This SOS must reach the backend before an operator can re-label it.');return;}
    const x=allRequests().find(r=>String(r.id)===String(id));if(!x)return;
    openModal(`<h2 id="modalTitle">Operator re-label</h2><p>Backend requires a reason for every control-room level change.</p><select id="newLevel" style="width:100%;padding:10px;border:1px solid var(--line);border-radius:7px"><option value="red">Red SOS · urgent</option><option value="yellow">Yellow SOS · need help</option></select><input id="reason" placeholder="Required reason" style="width:100%;padding:10px;margin-top:9px;border:1px solid var(--line);border-radius:7px"><div class="status-actions"><button class="btn wide" id="noRelabel">Cancel</button><button class="btn primary wide" id="yesRelabel">Save to backend</button></div>`);
    $('newLevel').value=x.level;$('noRelabel').onclick=closeModal;$('yesRelabel').onclick=async()=>{const reason=$('reason').value.trim();if(!reason){toast('A reason is required');return;}try{const result=await api(`/v1/sos/${encodeURIComponent(id)}/severity`,{method:'PATCH',body:JSON.stringify({severity:$('newLevel').value,actor:'control_room',reason})});window.disastraRequests=(window.disastraRequests||[]).map(r=>String(r.id)===String(id)?result:r);closeModal();renderQueue();redraw();toast('Level and reason saved to backend');}catch(e){toast(`Re-label failed: ${e.message}`);}};
  }
  async function selectRequest(id) {
    const raw=(window.disastraRequests||[]).find(r=>String(r.id)===String(id)); const row=raw?normalize(raw):allRequests().find(r=>String(r.id)===String(id));if(!row)return;
    selected=row;activeSOS=row;updateStatus(row);$('routeFor').textContent=`${row.level==='red'?'Red SOS · URGENT':'Yellow SOS · NEED HELP'} · ${row.id} · ${row.need} · ${row.people} people`;$('routeSeverity').textContent=row.level==='red'?'URGENT':'YELLOW';$('routeSeverity').className=`tag ${row.level==='yellow'?'yellow':''}`;
    if(Number.isFinite(Number(row.lat))&&Number.isFinite(Number(row.lon))){setLocation(Number(row.lat),Number(row.lon),'request');map?.setView([row.lat,row.lon],14);await loadFacilities(row.lat,row.lon);await loadRoutes(row);}
    else toast('Exact request location is unavailable. The backend returned a fuzzed public coordinate.');
    $('dispatchBtn').disabled=!(raw&&row.level==='red');renderQueue();
  }
  async function loadRoutes(row) {
    if(!row||!facilities.length)return;
    const destination=facilities.find(f=>!f.in_red_zone&&(selectedFacility?String(f.id)===String(selectedFacility):true))||facilities.find(f=>!f.in_red_zone);if(!destination)return;
    const body={origin:[Number(row.lon),Number(row.lat)],destination:[Number(destination.lon),Number(destination.lat)],vehicle_type:$('vehicleSelect').value?vehicles.find(v=>String(v.id)===$('vehicleSelect').value)?.type||'ambulance':'ambulance'};
    try{
      const [shortest,safe]=await Promise.all([api('/v1/route',{method:'POST',body:JSON.stringify({...body,avoid_hazards:false})}),api('/v1/route',{method:'POST',body:JSON.stringify({...body,avoid_hazards:true})})]);
      $('defaultRouteMetric').textContent=`${shortest.distance_km} km · ${shortest.duration_min} min`;$('safeRouteMetric').textContent=`${safe.distance_km} km · ${safe.duration_min} min · ${safe.risk_rating} risk`;
      $('routeRisk').textContent=`${safe.hazard_avoided?'Hazards avoided by backend route':'Backend found no intersecting Red hazard'} · confidence ${safe.confidence} · estimates are backend-generated.`;
      routesLayer.clearLayers();routeLayers=[];const draw=(r,color,dash)=>{const coords=r.route_geometry?.coordinates||[];if(coords.length>1)routeLayers.push(L.polyline(coords.map(c=>[c[1],c[0]]),{color,weight:color==='#43d19e'?5:3,dashArray:dash,opacity:.95}));};draw(shortest,'#a2b5c3','8 8');draw(safe,'#43d19e',null);redraw();
      $('dispatchBtn').disabled=row.level!=='red'||!rawIsBackend(row.id);
    }catch(e){$('routeRisk').textContent=`Routing unavailable: ${e.message}`;}
  }
  function rawIsBackend(id){return (window.disastraRequests||[]).some(r=>String(r.id)===String(id));}
  async function dispatch(id) {
    if(!rawIsBackend(id)){toast('This SOS must reach the backend before dispatch.');return;}
    const row=allRequests().find(x=>String(x.id)===String(id));if(!row){toast('Select a backend SOS before dispatch');return;}
    const doSend=async()=>{try{const result=await api('/v1/dispatch',{method:'POST',body:JSON.stringify({sos_ids:[id],vehicle_id:$('vehicleSelect').value?Number($('vehicleSelect').value):null,facility_id:$('destinationSelect').value?Number($('destinationSelect').value):null,batch:false})});closeModal();toast(`Dispatch ${result.id} created · provider alerts recorded`);await loadData({quiet:true});}
      catch(e){closeModal();toast(`Dispatch failed: ${e.message}`);}};
    openModal(`<h2 id="modalTitle">Confirm backend dispatch</h2><p><b>${row.level==='red'?'Red SOS · URGENT':'Yellow SOS · NEED HELP'}</b><br>${escapeHtml(row.id)} · ${escapeHtml(row.where)}<br>${$('destinationSelect').selectedOptions[0]?.textContent||'Automatic safe facility'}<br>Vehicle: ${$('vehicleSelect').selectedOptions[0]?.textContent||'Automatic match'}<br>Dispatch notification and facility pre-alert will be recorded by the backend.</p><div class="status-actions"><button class="btn wide" id="backDispatch">Review</button><button class="btn primary wide" id="yesDispatch">Dispatch now</button></div>`);$('backDispatch').onclick=closeModal;$('yesDispatch').onclick=doSend;
  }
  async function batchDispatch(){const ids=allRequests().filter(r=>r.level==='yellow'&&['received','pending','relayed','acknowledged'].includes(String(r.status).toLowerCase())).map(r=>r.id).filter(rawIsBackend);if(!ids.length){toast('No backend Yellow SOS requests are available to batch');return;}openModal(`<h2 id="modalTitle">Batch Yellow SOS</h2><p>Dispatch ${ids.length} Yellow SOS requests together using the backend facility and vehicle matcher.</p><button class="btn primary" id="approveBatch">Approve batch</button>`);$('approveBatch').onclick=async()=>{try{const out=await api('/v1/dispatch',{method:'POST',body:JSON.stringify({sos_ids:ids,batch:true})});closeModal();toast(`Yellow batch ${out.id} dispatched`);await loadData({quiet:true});}catch(e){toast(`Batch dispatch failed: ${e.message}`);}};}
  function reportRoad(){openModal(`<h2 id="modalTitle">Report road condition</h2><p>Tap the map to select the reported location, then submit a road status.</p><select id="roadStatus" style="width:100%;padding:10px;border:1px solid var(--line);border-radius:7px"><option value="blocked">Blocked</option><option value="clear">Clear</option></select><input id="roadSegment" placeholder="Road or segment name (optional)" style="width:100%;padding:10px;margin-top:9px;border:1px solid var(--line);border-radius:7px"><div class="status-actions"><button class="btn wide" id="cancelRoad">Cancel</button><button class="btn primary wide" id="submitRoad">Send report</button></div>`);$('cancelRoad').onclick=closeModal;$('submitRoad').onclick=async()=>{if(!selectedPoint){toast('Select the road location on the map first');return;}try{await api('/v1/road-report',{method:'POST',body:JSON.stringify({status:$('roadStatus').value,segment_id:$('roadSegment').value||null,reporter:'dashboard-operator',lat:selectedPoint[0],lon:selectedPoint[1]})});closeModal();toast('Road report saved to backend');await loadData({quiet:true});}catch(e){toast(`Road report failed: ${e.message}`);}};}
  document.addEventListener('click',e=>{
    const b=e.target.closest('[data-action]');if(!b)return;const id=b.dataset.id;
    if(b.dataset.action==='dispatch')dispatch(id);if(b.dataset.action==='select')selectRequest(id);if(b.dataset.action==='upgrade')upgrade(id);if(b.dataset.action==='relabel')relabel(id);
  });
  window.disastraLoad=loadData; window.disastraSelect=selectRequest;
  // Retain the current citizen flows, replacing their send/status actions with backend-backed calls.
  window.createSOS=createSOS;window.upgrade=upgrade;window.relabel=relabel;window.updateStatus=updateStatus;window.renderQueue=renderQueue;window.save=savePending;window.showPage=showPage;
  $('levelFilter').onchange=renderQueue;$('needFilter').onchange=renderQueue;
  $('dispatchBtn').onclick=()=>selected&&dispatch(selected.id);$('batchBtn').onclick=batchDispatch;$('roadReportBtn').onclick=reportRoad;
  $('refreshData').onclick=()=>loadData();$('apiBase').value=localStorage.getItem('disastra-api-base')||BASE;
  $('apiBase').addEventListener('change',()=>{localStorage.setItem('disastra-api-base',apiBase());loadData();});
  $('destinationSelect').addEventListener('change',()=>{selectedFacility=$('destinationSelect').value||null;if(selected)loadRoutes(selected);});$('vehicleSelect').addEventListener('change',()=>{if(selected)loadRoutes(selected);});
  $('locateMe').onclick=locate;document.querySelectorAll('[data-layer]').forEach(c=>c.addEventListener('change',()=>setLayer(c.dataset.layer,c.checked)));
  $('clusterToggle').onclick=()=>toast('Individual SOS markers are displayed; no clustering is applied to the loaded set.');
  $('zoomMap').onclick=()=>map?.zoomIn();
  $('enableAlerts').onclick=async()=>{try{const C=window.AudioContext||window.webkitAudioContext;if(C){const c=new C(),o=c.createOscillator(),g=c.createGain();o.frequency.value=760;g.gain.value=.035;o.connect(g);g.connect(c.destination);o.start();o.stop(c.currentTime+.16);}localStorage.setItem('disastra-voice','on');$('enableAlerts').textContent='✓ Alerts enabled';toast('Audible alert preview enabled');}catch{toast('Visual Red SOS alerts remain active');}};
  $('upgradeBtn').onclick=()=>selected&&selected.level==='yellow'&&upgrade(selected.id);
  $('cancelSOS').onclick=()=>toast('Cancellation is not supported by the current backend API. Contact the control room to update this request.');
  $('safeBtn').onclick=()=>toast('Safe check-in is not supported by the current backend API.');
  const originalShow=showPage;showPage=name=>{originalShow(name);setTimeout(()=>{map?.invalidateSize();citizenMap?.invalidateSize();},120);};
  initMaps();
  const checkbox=document.querySelector('[data-layer="facilities"]');if(checkbox)checkbox.checked=true;
  loadData({quiet:true});setInterval(()=>loadData({quiet:true}),15000);
  window.addEventListener('online',()=>{retryPending().then(()=>loadData({quiet:true}));});
})();
