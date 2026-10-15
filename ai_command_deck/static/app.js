'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const log = $('log');
  let list = [], selected = '', mode = 'live', player = null, playerKey = '';
  let signature = '', inFlight = false, last = '', paused = false, restoring = false;
  const positions = new Map();
  let speed=1, resumeTime=0, resumePlayback=false;
  const date = value => new Date(value).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
  const nearBottom = () => log.scrollHeight - log.clientHeight - log.scrollTop < 36;
  function savePosition() {
    if (selected && !restoring) positions.set(selected, {top:log.scrollTop,left:log.scrollLeft,follow:$('follow').checked});
  }
  function follow() {
    $('latest').hidden = $('follow').checked;
    if ($('follow').checked) log.scrollTop = log.scrollHeight;
  }
  log.addEventListener('scroll', () => {
    if (restoring) return;
    $('follow').checked = nearBottom();
    $('latest').hidden = $('follow').checked;
    savePosition();
  }, {passive:true});
  $('follow').onchange = () => {follow(); savePosition();};
  $('latest').onclick = () => {$('follow').checked=true;follow();savePosition();};
  $('wrap').onchange = () => {log.classList.toggle('nowrap', !$('wrap').checked);follow();};
  $('pause').onclick = () => {paused=!paused;$('pause').textContent=paused?'继续更新':'暂停更新';refresh();};
  $('copy').onclick = async () => {
    try {await navigator.clipboard.writeText(log.textContent);$('copy').textContent='已复制';}
    catch {$('copy').textContent='复制失败';}
    setTimeout(() => $('copy').textContent='复制输出', 1500);
  };
  function dispose() {
    if (player) player.dispose();
    player=null;playerKey='';$('player').replaceChildren();
  }
  function renderPlayer(item) {
    const key = `${selected}:${mode}:${Boolean(item?.recording)}:${Boolean(item?.active)}:${speed}`;
    if (key === playerKey) return;
    dispose(); playerKey=key;
    $('empty').hidden = Boolean(item);
    if (!item || mode === 'text') return;
    if (!item.recording) return;
    const options = {theme:'asciinema',fit:false,controls:mode==='replay',speed,startAt:mode==='replay'?resumeTime:0,terminalFontFamily:'Menlo, Consolas, monospace',terminalFontSize:'13px',terminalLineHeight:1.3,preload:true,autoPlay:(mode==='live'&&item.active)||resumePlayback,idleTimeLimit:2};
    if(mode==='live'&&!item.active)options.poster=`npt:${item.duration??0}`;
    resumeTime=0;resumePlayback=false;
    const source = mode === 'live'&&item.active
      ? `ws://${location.host}/api/live/${selected}`
      : `/api/cast/${selected}`;
    try {
      player=AsciinemaPlayer.create(source,$('player'),options);
      player.addEventListener('error', () => {$('summary').textContent='终端播放器加载失败，请切换文本日志或刷新重试';});
    } catch {
      $('summary').textContent='终端播放器不可用，请切换文本日志';
    }
  }
  function renderSessions() {
    const key=JSON.stringify([list,selected,$('filter').value]);
    if(key===signature)return;
    signature=key;
    const container=$('sessions'),top=container.scrollTop,left=container.scrollLeft;
    const focusId=document.activeElement?.dataset?.session;
    const nodes=[];
    for(const item of list) {
      if(!item.name.toLowerCase().includes($('filter').value.toLowerCase()))continue;
      const button=document.createElement('button');button.className='session'+(item.id===selected?' selected':'');
      button.dataset.session=item.id;button.setAttribute('aria-pressed',String(item.id===selected));
      const name=document.createElement('div');name.className='session-name';name.textContent=item.name;
      const meta=document.createElement('div');meta.className='session-meta'+(item.active?' running':'');
      meta.textContent=(item.active?'● 运行中':'○ 已结束')+' · '+date(item.created);
      button.append(name,meta);button.onclick=()=>choose(item.id);nodes.push(button);
    }
    container.replaceChildren(...nodes);container.scrollTop=top;container.scrollLeft=left;
    if(focusId)[...container.children].find(n=>n.dataset.session===focusId)?.focus({preventScroll:true});
    $('count').textContent=`${list.length} 个`;
  }
  function choose(id) {
    if(id===selected)return;
    savePosition();selected=id;last='';restoring=true;log.textContent='正在读取…';
    const saved=positions.get(id);$('follow').checked=saved?.follow??true;
    const item=list.find(x=>x.id===id);
    if(item&&!item.recording)mode='text';
    render();refresh();
  }
  function setMode(next) {
    savePosition();mode=next;render();refresh();
  }
  $('speed').onclick=()=>{resumeTime=player?.getCurrentTime()??0;resumePlayback=true;const rates=[0.5,1,1.5,2,4];speed=rates[(rates.indexOf(speed)+1)%rates.length];render();};
  $('live-tab').onclick=()=>setMode('live');$('replay-tab').onclick=()=>setMode('replay');$('text-tab').onclick=()=>setMode('text');
  $('filter').oninput=renderSessions;
  function render() {
    const item=list.find(x=>x.id===selected);
    if(item&&!item.recording)mode='text';
    renderSessions();
    $('title').textContent=item?.name??'等待终端会话';
    $('detail').textContent=item?(item.active?'运行中 · 命令与输出实时记录':`已结束 · ${item.duration!=null?item.duration.toFixed(1)+' 秒 · ':''}${item.exit_code!=null?'退出码 '+item.exit_code+' · ':''}本机保存`):'启动一个会话，即可实时查看命令执行';
    for(const name of ['live','replay','text'])$(name+'-tab').setAttribute('aria-selected',String(mode===name));
    $('live-tab').disabled=!item?.recording;$('replay-tab').disabled=!item?.recording||item.active;
    $('terminal-view').classList.toggle('live',mode==='live');
    $('terminal-view').hidden=mode==='text';$('text-view').hidden=mode!=='text';
    $('download').hidden=!item?.recording||item.active;
    if(item?.recording)$('download').href=`/api/cast/${selected}?download=1`;
    $('speed').hidden=mode!=='replay';$('speed').textContent=`倍速 ${speed}×`;
    $('mode-hint').textContent=mode==='text'?'TEXT LOG':mode==='live'?'LIVE · ASCIINEMA':'REPLAY · ASCIINEMA';
    if(mode!=='text')$('summary').textContent=!item?'选择会话开始查看':mode==='replay'?'拖动时间轴 · 支持倍速播放':item.active?'实时终端 · 浏览器仅供查看':'终端最终画面 · 切换历史回放查看完整过程';
    renderPlayer(item);
  }
  async function refreshText() {
    if(!selected||paused||mode!=='text')return;
    const id=selected,response=await fetch(`/api/log/${id}`);
    if(!response.ok)throw Error('Log unavailable');
    const text=await response.text();
    if(id!==selected||mode!=='text')return;
    if(text!==last) {
      const first=!last,following=$('follow').checked,top=log.scrollTop,left=log.scrollLeft;
      if(last&&text.startsWith(last))log.append(document.createTextNode(text.slice(last.length)));
      else log.textContent=text;
      last=text;
      if(following)log.scrollTop=log.scrollHeight;
      else {const saved=positions.get(id);log.scrollTop=first?(saved?.top??top):top;log.scrollLeft=first?(saved?.left??left):left;}
      if(restoring)requestAnimationFrame(()=>{restoring=false;savePosition();});
    } else if(restoring)restoring=false;
    follow();$('summary').textContent=`${text?text.split('\n').length:0} 行 · 最近最多 500 KB`;
  }
  async function refresh() {
    if(inFlight)return;
    inFlight=true;
    try {
      const response=await fetch('/api/sessions');if(!response.ok)throw Error();
      list=await response.json();
      if(selected&&!list.some(x=>x.id===selected)){dispose();selected='';last='';log.textContent='';}
      if(!selected&&list.length)selected=list[0].id;
      render();await refreshText();
      $('state').textContent='● 本机已连接';
      $('updated').textContent=paused&&mode==='text'?'显示已暂停 · 记录继续':'已同步 '+new Date().toLocaleTimeString('zh-CN');
    } catch {$('state').textContent='连接中断 · 正在重试';}
    finally {inFlight=false;}
  }
  fetch('/api/config').then(r=>r.json()).then(config=>$('days').textContent=config.retention_days).catch(()=>{});
  window.addEventListener('beforeunload',dispose);
  refresh();setInterval(refresh,700);
})();
