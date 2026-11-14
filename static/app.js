const byId = id => document.getElementById(id);
const start = byId('start'), record = byId('record'), retry = byId('retry'), player = byId('player');
let call, capture, pending, timer;
function line(role, words) {
  const item = document.createElement('li'), label = document.createElement('b');
  label.textContent = role; item.append(label, document.createTextNode(words)); byId('log').append(item);
}
async function json(url, options) {
  const response = await fetch(url, options), result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}
async function show(next) {
  call = next;
  if (call.heard) line('Caller', call.heard);
  line('Agent', call.prompt);
  player.hidden = false;
  player.src = '/calls/' + call.call_id + '/speech/' + call.seq;
  byId('status').textContent = '';
  try { await player.play(); } catch { byId('status').textContent = 'Use the audio player to hear the prompt.'; }
  const closed = ['opened','cancelled'].includes(call.stage);
  record.hidden = closed; record.disabled = false; start.hidden = !closed;
  if (call.case_id) { const link = byId('case'); link.hidden = false; link.href = '/cases/'+call.case_id; }
}
start.onclick = async () => {
  start.disabled = true;
  try {
    const next = await json('/calls',{method:'POST'}); byId('log').replaceChildren();
    byId('case').hidden = true; start.hidden = true; await show(next);
  } catch (e) { byId('status').textContent = e.message; }
  finally { start.disabled = false; }
};
function wav(chunks, rate) {
  const samples = new Float32Array(chunks.reduce((n,c)=>n+c.length,0));
  let cursor = 0; for (const chunk of chunks) { samples.set(chunk,cursor); cursor += chunk.length; }
  const count = Math.min(480000, Math.floor(samples.length*16000/rate));
  const buf = new ArrayBuffer(44+count*2), view = new DataView(buf);
  function tag(i,s) { for(const c of s) view.setUint8(i++,c.charCodeAt(0)); }
  tag(0,'RIFF');view.setUint32(4,36+2*count,true);tag(8,'WAVEfmt ');view.setUint32(16,16,true);
  view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);
  view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);tag(36,'data');view.setUint32(40,count*2,true);
  for(let i=0;i<count;i++) {
    const a=Math.floor(i*rate/16000), b=Math.max(a+1,Math.floor((i+1)*rate/16000));
    let total=0;for(let j=a;j<b;j++) total+=samples[j];
    view.setInt16(44+i*2,Math.round(Math.max(-1,Math.min(1,total/(b-a)))*32767),true);
  }
  return new Blob([buf],{type:'audio/wav'});
}
async function upload() {
  record.disabled = true; retry.hidden = true; byId('status').textContent='Transcribing your reply…';
  try {
    const next=await json('/calls/'+call.call_id+'/turns',{method:'POST',headers:{'Content-Type':'audio/wav',
      'X-Sequence':String(call.seq),'Idempotency-Key':pending.id},body:pending.audio});
    pending=null; await show(next);
  } catch(e) { byId('status').textContent=e.message; retry.hidden=false; }
  finally { record.disabled=false; }
}
retry.onclick=upload;
record.onclick=async()=>{
  record.disabled=true;
  try {
    if (capture) {
      clearTimeout(timer); const {stream,context,node,chunks}=capture; capture=null;
      node.disconnect();stream.getTracks().forEach(t=>t.stop());
      const audio=wav(chunks,context.sampleRate);await context.close();
      pending={id:crypto.randomUUID(),audio}; record.textContent='Record reply'; await upload();
    } else {
      player.pause();retry.hidden=true;
      const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true}});
      try {
        const context=new AudioContext();await context.resume();
        const source=context.createMediaStreamSource(stream),node=context.createScriptProcessor(4096,1,1),chunks=[];
        node.onaudioprocess=e=>chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
        source.connect(node);node.connect(context.destination);capture={stream,context,node,chunks};
        byId('status').textContent='Listening. Stop when you finish speaking.';record.textContent='Stop and send';
        timer=setTimeout(()=>record.click(),29500);
      } catch(e) { stream.getTracks().forEach(t=>t.stop());throw e; }
    }
  } catch(e) { byId('status').textContent=e.message; }
  finally { record.disabled=false; }
};
