/**
 * Repo Dragon v3.4 — seated-pose recovery bridges, stabilized curious frames, responsive ambient life.
 * Standalone local proof of concept. Does not write to GitHub or GitHub Pages.
 */
(()=>{
'use strict';
const $=id=>document.getElementById(id);
const widget=$('dragon'), tiltLayer=$('dragon-tilt');
const sprites=[$('dragon-sprite-a'),$('dragon-sprite-b')];
const gazeCanvas=$('dragon-eyes'),ctx=gazeCanvas.getContext('2d');
const status=$('dragon-state'),hint=$('current-behavior');
const btnPause=$('toggle-animation'),btnFire=$('test-fire'),btnReset=$('reset-dragon');
const btnCurious=$('test-curious'),btnTune=$('tune-toggle'),tunePanel=$('tune-panel');
const sliderThreshold=$('scroll-threshold'),sliderDelay=$('scroll-delay');
const valThreshold=$('threshold-value'),valDelay=$('delay-value');
const clips={sleep:60,wake:24,fly:24,land:30,grab:30,fire:45,idle:48,
  'curious-look':48,'curious-tilt':48,'curious-peek':48,'curious-blink':37,
  'curious-wing':48,'curious-tail':48,'curious-stretch':48};
// Avoid perpetual head-rocking: only finite, localized gestures auto-play.
const curious=['curious-blink','curious-look'];
const recoveryNames=['land','fire','curious-look','curious-tilt','curious-peek',
  'curious-blink','curious-wing','curious-tail','curious-stretch'];
for (const name of recoveryNames)clips['sit-from-'+name]=18;
const loopClips=new Set(['sleep','fly']);
const duration={sleep:2000,wake:900,fly:800,land:1580,grab:1150,fire:2750,idle:2000,
  'curious-look':2400,'curious-tilt':2650,'curious-peek':2600,
  'curious-blink':1250,'curious-wing':2500,'curious-tail':2450,'curious-stretch':2670};
for(const name of recoveryNames)duration['sit-from-'+name]=580;
const clamp=(v,l,r)=>Math.max(l,Math.min(r,v));
const lerp=(a,b,t)=>a+(b-a)*t;
const smooth=t=>{t=clamp(t,0,1);return t*t*(3-2*t);};
const clock=()=>performance.now();
const rand=(a,b)=>a+Math.random()*(b-a);
const anchors=[...document.querySelectorAll('[data-dragon-anchor]')];
let phase='sleep',phaseAt=clock(),frame=-1,activeLayer=0,playing=true;
let pos={x:0,y:0},target={x:0,y:0},flight=null;
let drag=null,manual=false, scrollDirection=1,lastScrollY=scrollY;
let scrollAccum=0,firstScrollAt=0,lastScrollAt=0,scrollIntent=false;
let nextCuriousAt=clock()+3400,nextFireAt=clock()+26000,lastCurious=-1;
let lastAt=clock(),face=1,tilt=0,pausedAt=0;
let hoveredAt=0,hoverConsumed=false,beStillUntil=0,activeAnchor='intro',lastRetargetAt=0;
let pendingTravel=160;
let threshold=Number(sliderThreshold?.value||135);
let reactionDelay=Number(sliderDelay?.value||200);
const reduceMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
if(reduceMotion)playing=false;
const mouse={x:-3000,y:-3000},look={x:0,y:0};
const size=()=>parseFloat(getComputedStyle(widget).width)||152;
function boundaries(x,y){
  const w=size(),height=Math.max(document.documentElement.scrollHeight,document.body.scrollHeight);
  return {x:clamp(x,8,Math.max(8,document.documentElement.clientWidth-w-8)),
    y:clamp(y,8,Math.max(8,height-w-10))};
}
function setPoint(p){const q=boundaries(p.x,p.y);target={...q};pos={...q};}
function visibleSection(){
  let nearest=anchors[0],best=Infinity;
  const focus=innerHeight*.44;
  for(const a of anchors){
    const r=a.getBoundingClientRect();
    const distance=r.top>focus?r.top-focus:(r.bottom<focus?focus-r.bottom:0);
    if(distance<best){nearest=a;best=distance;}
  }
  return nearest;
}
function pointFor(a){
  const w=size(),section=a||visibleSection();
  const pageX=scrollX,pageY=scrollY;
  const content=document.querySelector('.markdown-body').getBoundingClientRect();
  const r=section.getBoundingClientRect();
  let x=content.right + pageX-w*.95;
  let y=r.top+pageY+30;
  if(section.id==='intro'){
    const title=document.querySelector('.intro h1').getBoundingClientRect();
    y=title.top+pageY-14;
  } else if(section.id==='tech')y=r.top+pageY+95;
  else if(section.id==='contact')y=r.bottom+pageY-w*.9-12;
  else if(section.id==='personal')y=r.top+pageY+25;
  else y=r.top+pageY+35;
  return boundaries(x,y);
}
// The target is a physical DOCUMENT coordinate: not window.scrollY + a permanent viewport offset.
// As a result, when the page scrolls, Repo naturally scrolls with the section it sits on.
function scrollGoal(travel=threshold){
  const section=visibleSection();
  const p=pointFor(section);
  // Prefer a visible safe landing point on the section's right margin.
  // If its header is already above/below the view (or we're already perched
  // on it), walk/fly to a fresh world-coordinate waypoint inside the view.
  const screenY=p.y-scrollY;
  if(screenY<90 || screenY>innerHeight*.67 || Math.hypot(p.x-pos.x,p.y-pos.y)<Math.max(40,size()*.38)){
    const landingHeight=clamp(innerHeight*.38,185,340);
    const desired=scrollY+landingHeight;
    // The waypoint is chosen only when scroll intent fires, not each scroll tick.
    p.y=desired;
  }
  return boundaries(p.x,p.y);
}
function beginFlight(p,t,asRetarget=false){
  p=boundaries(p.x,p.y);
  const distance=Math.hypot(p.x-pos.x,p.y-pos.y);
  if(distance<13){flight=null;target=p;pos=p;return false;}
  const seconds=clamp(distance/580,.70,1.65);
  const side=scrollDirection>0?-1:1;
  flight={from:{...pos},to:{...p},start:t,duration:seconds*1000,
    arc:side*clamp(distance*.19,25,92)};
  target=p;lastRetargetAt=t;
  if(phase!=='fly')setState('fly');
  return true;
}
function sampleFlight(t){
  if(!flight)return;
  const progress=clamp((t-flight.start)/flight.duration,0,1);
  const ease=smooth(progress),arch=Math.sin(Math.PI*progress);
  pos.x=lerp(flight.from.x,flight.to.x,ease)+flight.arc*arch;
  pos.y=lerp(flight.from.y,flight.to.y,ease)-Math.min(36,Math.abs(flight.to.y-flight.from.y)*.05+10)*arch;
  if(progress>=1){pos={...flight.to};flight=null;}
}
function initImage(el,clip){el.style.backgroundImage=`url('dragon/${clip}-sprite.webp')`;}
function showFrame(el,n){el.style.backgroundPosition=`${-(n%8)*256}px ${-Math.floor(n/8)*256}px`;}
function setState(next,{force=false}={}){
  if(!clips[next]||(phase===next&&!force))return;
  const old=phase,nextLayer=1-activeLayer;
  const outgoing=sprites[activeLayer],incoming=sprites[nextLayer];
  initImage(incoming,next);showFrame(incoming,0);
  // Longer blends connect held silhouettes without looping the resting pose.
  // Grab remains instantaneous; delays belong to transitions, not pointer movement.
  // Bridges match the exact first/last rasterized pose. Switching to or from
  // them is immediate; the bridge ITSELF supplies 18 drawn/morphed frames.
  const isBridge=(next.startsWith('sit-from-')||old.startsWith('sit-from-'));
  const fade=isBridge?0:(next==='grab')?80:(next==='fly'||old==='fly')?200:
    (next==='land'||old==='land')?150:(next==='sleep'||old==='sleep')?300:250;
  outgoing.style.transitionDuration=`${fade}ms`;incoming.style.transitionDuration=`${fade}ms`;
  incoming.style.opacity='0';void incoming.offsetWidth;
  incoming.style.opacity='1';outgoing.style.opacity='0';
  activeLayer=nextLayer;phase=next;phaseAt=clock();frame=-1;
  widget.dataset.pose=next;
  status.textContent=next.toUpperCase().replace('CURIOUS-','LOOK: ');
  hint.textContent=next.startsWith('curious-')?'Curious · '+next.slice(8)
    :({sleep:'Ngủ tại đầu trang',wake:'Tỉnh dậy',fly:'Bay giữa các mục trong trang',
    land:'Chạm đất, thu cánh',idle:'Ngồi yên (tư thế gốc)',grab:'Kéo trực tiếp, không trễ',
    fire:'Phun lửa'})[next] || (next.startsWith('sit-from-')?'Thu cánh, hạ người, ngồi lại':'');
  gazeCanvas.style.opacity=next==='curious-look'?'1':'0';
}
function renderSprite(t){
  const n=clips[phase],time=t-phaseAt;
  let k;
  if(phase==='idle')k=0; // Truly still between actions: no rocking, bobbing, or perpetual sway.
  else if(phase==='curious-look')k=0; // Head stays still; only the pupils ease toward the pointer.
  else if(phase==='land'){
    // Approach -> feet touch -> wings tuck. End at EXACT frame 16 so the
    // per-source sit-from-land bridge starts from the same silhouette.
    const p=clamp(time/duration.land,0,1);
    k=Math.round(16*smooth(p));
  }
  else if(phase==='grab')k=clamp(Math.floor(time/85),0,12); // hold dragged pose
  else if(loopClips.has(phase))k=Math.floor((time%duration[phase])/duration[phase]*n);
  else k=clamp(Math.floor(time/duration[phase]*n),0,n-1);
  if(k!==frame){showFrame(sprites[activeLayer],k);frame=k;}
}
// Independent timers: curiosities must never postpone the occasional fire forever.
function stillSchedule(t,{newFire=false}={}){
  nextCuriousAt=t+rand(2850,4400);
  if(newFire)nextFireAt=t+rand(21000,32000);
}
function idle(t){
  flight=null;setState('idle');beStillUntil=t+850;
  // A real quiet pause between expressive beats, but not ten seconds of silence.
  stillSchedule(t);
}
function settle(t){
  flight=null;setState('land');beStillUntil=t+duration.land;
}
function returnToSit(outgoing){
  if(recoveryNames.includes(outgoing)){
    setState('sit-from-'+outgoing);
  }else idle(clock());
}
function wake(t){setState('wake');beStillUntil=t+420;}
function chooseCurious(t,requested=null){
  let i=requested===null?Math.floor(Math.random()*curious.length):requested;
  if(typeof i==='number'&&i===lastCurious)i=(i+1)%curious.length;
  if(typeof i==='number'){lastCurious=i;setState(curious[i]);}
  else setState(i);
}
function onScroll(){
  const y=scrollY,dy=y-lastScrollY;lastScrollY=y;
  if(!playing||drag||Math.abs(dy)<1.5)return;
  const t=clock();scrollDirection=Math.sign(dy)||scrollDirection;lastScrollAt=t;
  if(firstScrollAt===0||t-firstScrollAt>550){firstScrollAt=t;scrollAccum=0;}
  scrollAccum=clamp(scrollAccum+Math.abs(dy),0,2000);scrollIntent=true;
  if(phase==='fly'&&flight){
    const section=visibleSection();
    // Retarget only if we've entered ANOTHER actual section, never for each wheel tick.
    if(section.id!==activeAnchor&&t-lastRetargetAt>400){
      activeAnchor=section.id;beginFlight(pointFor(section),t,true);
    }
  }
}
function resolveScroll(t){
  if(!scrollIntent||drag||!playing)return;
  if(t-firstScrollAt<reactionDelay)return;
  if(scrollAccum>=threshold){
    pendingTravel=scrollAccum;
    scrollIntent=false;scrollAccum=0;firstScrollAt=0;
    const section=visibleSection();activeAnchor=section.id;
    manual=false;
    if(phase==='sleep')wake(t);
    else if(phase==='fly' && flight){
      // Long wheel streams must not restart the path every 200 ms.
      const goal=scrollGoal(pendingTravel);
      if(t-lastRetargetAt>650 && Math.hypot(goal.x-flight.to.x,goal.y-flight.to.y)>175)
        beginFlight(goal,t,true);
    } else beginFlight(scrollGoal(pendingTravel),t);
  } else if(t-lastScrollAt>550){scrollIntent=false;scrollAccum=0;firstScrollAt=0;}
}
function nearMouse(){
  const v={x:pos.x-scrollX,y:pos.y-scrollY};
  return Math.hypot(mouse.x-(v.x+size()*.5),mouse.y-(v.y+size()*.46))<size()*1.35;
}
function updateEyes(dt){
  const relevant=phase==='curious-look'&&nearMouse();
  const localX=mouse.x-(pos.x-scrollX)-size()*.50;
  const localY=mouse.y-(pos.y-scrollY)-size()*.48;
  const desiredX=relevant?clamp(localX/size()*.7,-1,1):0;
  const desiredY=relevant?clamp(localY/size()*.7,-1,1):0;
  const factor=1-Math.exp(-dt/520);
  look.x+=(desiredX-look.x)*factor;look.y+=(desiredY-look.y)*factor;
  ctx.clearRect(0,0,256,256);
  if(phase!=='curious-look')return;
  for(const [x,y,r] of [[136,124,4.2],[184,115,3.1]]){
    const px=x+look.x*2.7,py=y+look.y*2;
    ctx.beginPath();ctx.ellipse(px,py,r,r*1.14,0,0,Math.PI*2);
    ctx.fillStyle='rgba(10,31,43,.64)';ctx.fill();
    ctx.beginPath();ctx.arc(px-r*.4,py-r*.5,r*.28,0,Math.PI*2);
    ctx.fillStyle='rgba(245,255,255,.82)';ctx.fill();
  }
}
function behavior(t){
  resolveScroll(t);
  if(phase==='wake'&&t-phaseAt>duration.wake){
    if(!beginFlight(scrollGoal(pendingTravel),t))settle(t);
    return;
  }
  if(phase==='fly'){
    // Stop changing target every animation frame. Follow one anchor in page-space.
    if(!flight && t-lastScrollAt>330){settle(t);return;}
    if(!flight && t-lastScrollAt<=330){
      // Hold the flying pose briefly so that active scrolling can select another section.
      return;
    }
    return;
  }
  if(phase==='land'&&t-phaseAt>=duration.land){returnToSit('land');return;}
  if(phase==='fire'&&t-phaseAt>=duration.fire){returnToSit('fire');return;}
  if(phase.startsWith('curious-')&&t-phaseAt>=duration[phase]){returnToSit(phase);return;}
  if(phase.startsWith('sit-from-')&&t-phaseAt>=duration[phase]){
    // Last bridge frame is pixel-identical to IDLE #0. No hard pose cut.
    idle(t);return;
  }
  if(phase==='idle'){
    const nearby=nearMouse();
    // Treat hovering as one deliberate interaction, not a repeating head wobble.
    if(!nearby){hoveredAt=0;hoverConsumed=false;}
    else if(!hoveredAt)hoveredAt=t;
    if(t<beStillUntil)return;
    if(scrollY<35&&!manual&&t-phaseAt>11000){setState('sleep');return;}
    if(nearby&&!hoverConsumed&&t-hoveredAt>1450){
      hoverConsumed=true;chooseCurious(t,'curious-look');return;
    }
    // Allow fire to happen even after multiple curiosity actions.
    if(t>=nextFireAt&&!nearby){
      nextFireAt=t+rand(29000,47000);setState('fire');return;
    }
    if(t>=nextCuriousAt){
      chooseCurious(t);return;
    }
  }
}
function animate(t){
  const dt=clamp(t-lastAt,0,42);lastAt=t;
  if(playing){
    if(!drag)behavior(t);
    if(flight&&!drag)sampleFlight(t);
    renderSprite(t);updateEyes(dt);
  }
  // No CSS bob, tilt, rocking, spring rebound or inertia outside actual travel.
  // Character motion is fully inside finite sprites; the world coordinate is fixed at rest.
  face=phase==='fly'?(scrollDirection>0?1:-1):1;
  tiltLayer.style.transform=`scaleX(${face})`;
  widget.style.transform=`translate3d(${pos.x.toFixed(2)}px,${pos.y.toFixed(2)}px,0)`;
  requestAnimationFrame(animate);
}
function reset(){
  drag=null;manual=false;flight=null;scrollIntent=false;scrollAccum=0;firstScrollAt=0;
  lastScrollY=scrollY;activeAnchor=visibleSection().id;
  const start=pointFor(visibleSection());
  if(scrollY>35 && (start.y-scrollY<70 || start.y-scrollY>innerHeight*.75))
    start.y=scrollY+clamp(innerHeight*.38,185,340);
  setPoint(start);tilt=0;
  setState(scrollY<35?'sleep':'idle',{force:true});stillSchedule(clock(),{newFire:true});
}
widget.addEventListener('pointerdown',e=>{
  if(!playing||!e.isPrimary)return;
  e.preventDefault();widget.setPointerCapture(e.pointerId);
  // Preserve the EXACT pick-up offset so the dragon doesn't jump under the cursor.
  drag={id:e.pointerId,startX:e.clientX,startY:e.clientY,
    offsetX:(e.clientX+scrollX)-pos.x,offsetY:(e.clientY+scrollY)-pos.y,moved:false};
});
widget.addEventListener('pointermove',e=>{
  if(!drag||e.pointerId!==drag.id)return;
  const distance=Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY);
  if(!drag.moved&&distance>5){
    drag.moved=true;flight=null;setState('grab');widget.classList.add('dragging');
  }
  if(!drag.moved)return;
  // Direct movement: no acceleration, no damping or delayed follow while held.
  const q=boundaries(e.clientX+scrollX-drag.offsetX,e.clientY+scrollY-drag.offsetY);
  pos={...q};target={...q};
});
function release(e){
  if(!drag||e.pointerId!==drag.id)return;
  const moved=drag.moved;
  if(widget.hasPointerCapture(e.pointerId))widget.releasePointerCapture(e.pointerId);
  drag=null;widget.classList.remove('dragging');
  if(moved){manual=true;target={...pos};settle(clock());}
  else {hoverConsumed=true;chooseCurious(clock(),'curious-peek');}
  stillSchedule(clock());
}
widget.addEventListener('pointerup',release);
widget.addEventListener('pointercancel',release);
widget.addEventListener('keydown',e=>{
  if(!playing)return;
  if(e.key==='Enter'||e.key===' '){e.preventDefault();chooseCurious(clock(),'curious-tilt');}
  if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)){
    e.preventDefault();manual=true;flight=null;
    const delta=18;
    setPoint(boundaries(pos.x+(e.key==='ArrowRight'?delta:e.key==='ArrowLeft'?-delta:0),
      pos.y+(e.key==='ArrowDown'?delta:e.key==='ArrowUp'?-delta:0)));
    setState('idle');
  }
});
window.addEventListener('pointermove',e=>{mouse.x=e.clientX;mouse.y=e.clientY;},{passive:true});
window.addEventListener('scroll',onScroll,{passive:true});
window.addEventListener('resize',()=>{
  const p=boundaries(pos.x,pos.y);pos={...p};
  if(!manual&&!drag&&!flight)target=pointFor(visibleSection());
},{passive:true});
btnFire.addEventListener('click',()=>{if(playing&&!drag){flight=null;nextFireAt=clock()+rand(29000,47000);setState('fire');}});
btnCurious.addEventListener('click',()=>{if(playing&&!drag)chooseCurious(clock(),(lastCurious+1)%curious.length);});
btnReset.addEventListener('click',()=>{playing=true;btnPause.textContent='Pause';btnPause.setAttribute('aria-pressed','true');reset();});
btnPause.addEventListener('click',()=>{
  playing=!playing;btnPause.textContent=playing?'Pause':'Resume';
  btnPause.setAttribute('aria-pressed',String(playing));widget.style.opacity=playing?'1':'.55';
  if(playing){phaseAt=clock();scrollIntent=false;scrollAccum=0;flight=null;lastScrollY=scrollY;}
});
btnTune.addEventListener('click',()=>{
  const expanded=btnTune.getAttribute('aria-expanded')==='true';
  btnTune.setAttribute('aria-expanded',String(!expanded));tunePanel.hidden=expanded;
});
sliderThreshold.addEventListener('input',()=>{threshold=Number(sliderThreshold.value);valThreshold.textContent=`${threshold} px`;});
sliderDelay.addEventListener('input',()=>{reactionDelay=Number(sliderDelay.value);valDelay.textContent=`${reactionDelay} ms`;});
for(const clip of Object.keys(clips)){const image=new Image();image.src=`dragon/${clip}-sprite.webp`;}
initImage(sprites[0],'sleep');sprites[0].style.opacity='1';sprites[1].style.opacity='0';
if(reduceMotion){btnPause.textContent='Resume';btnPause.setAttribute('aria-pressed','false');widget.style.opacity='.7';}
reset();requestAnimationFrame(animate);
window.__repoDragonDebug=()=>({phase,pos:{...pos},target:{...target},
  viewport:{x:pos.x-scrollX,y:pos.y-scrollY},flight:flight?{from:flight.from,to:flight.to}:null,
  scrollY,activeAnchor,manual,dragging:!!drag,threshold,reactionDelay,playing,
  nextCuriousInMs:Math.round(nextCuriousAt-clock()),nextFireInMs:Math.round(nextFireAt-clock()),
  hasHoverBeenHandled:hoverConsumed,bridge:phase.startsWith('sit-from-'),
  idleIsStill:phase==='idle'&&!flight});
})();
