function cleanEmail(){
  const copy=document.getElementById('email').cloneNode(true);
  copy.removeAttribute('id');copy.removeAttribute('contenteditable');copy.removeAttribute('spellcheck');
  copy.querySelectorAll('script,style,iframe,object,embed,form,input,button,img,video,audio').forEach(n=>n.remove());
  copy.querySelectorAll('*').forEach(el=>Array.from(el.attributes).forEach(a=>{
    if(a.name.startsWith('on')||a.name==='contenteditable'||a.name==='srcdoc')el.removeAttribute(a.name);
    if(a.name==='href'&&!/^(https?:\/\/|#)/i.test(a.value))el.removeAttribute(a.name);
  }));
  return copy.innerHTML;
}
async function copyEmail(){
  const markup=cleanEmail();
  try{
    const tmp=document.createElement('div');tmp.innerHTML=markup;
    if(window.ClipboardItem&&navigator.clipboard?.write){
      await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([markup],{type:'text/html'}),'text/plain':new Blob([tmp.innerText],{type:'text/plain'})})]);
    }else{throw new Error('Clipboard unavailable');}
    document.getElementById('feedback').textContent='Email copied. Paste it into your draft.';
  }catch(err){
    const range=document.createRange();range.selectNodeContents(document.getElementById('email'));
    const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
    document.getElementById('feedback').textContent='Email selected. Press Ctrl+C to copy it, or download the edited .eml.';
  }
}
function b64(value){const bytes=new TextEncoder().encode(value);let s='';bytes.forEach(b=>s+=String.fromCharCode(b));return btoa(s);}
function downloadEmail(){
  const meta=JSON.parse(document.getElementById('draft-meta').textContent);
  const markup='<!doctype html><html><head><meta charset="utf-8"></head><body>'+cleanEmail()+'</body></html>';
  const subjectBytes=new TextEncoder().encode(meta.subject);let chunks=[];let chunk='';let size=0;
  for(const ch of meta.subject){const n=new TextEncoder().encode(ch).length;if(size+n>39){chunks.push(chunk);chunk='';size=0;}chunk+=ch;size+=n;}if(chunk)chunks.push(chunk);
  const subject=chunks.map(c=>'=?UTF-8?B?'+b64(c)+'?=').join('\r\n ');
  const content=b64(markup).match(/.{1,76}/g).join('\r\n');
  const eml='Subject: '+subject+'\r\nDate: '+meta.date+'\r\nX-Unsent: 1\r\nMIME-Version: 1.0\r\nContent-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n'+content+'\r\n';
  const url=URL.createObjectURL(new Blob([eml],{type:'message/rfc822'}));const a=document.createElement('a');a.href=url;a.download='morning-note-edited.eml';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
  document.getElementById('feedback').textContent='Edited email downloaded. No message was sent.';
}
