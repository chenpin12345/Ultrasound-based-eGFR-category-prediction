// No case identifiers, images, session tokens or clinical content leave this tab.
type Change = {type:'clinical-change'; clear:boolean; scope:'all'|'pdf'}
const listeners=new Set<(clear:boolean,scope:'all'|'pdf')=>void>()
let channel:BroadcastChannel|undefined
function receive(value:unknown) {
  if(!value||typeof value!=='object')return
  const change=value as Change
  if(change.type!=='clinical-change'||typeof change.clear!=='boolean'||!['all','pdf'].includes(change.scope))return
  for(const listener of listeners)listener(change.clear,change.scope)
}
function connect() {
  if(!channel&&typeof BroadcastChannel!=='undefined') {
    channel=new BroadcastChannel('isu-clinical-invalidation-v1')
    channel.onmessage=event=>receive(event.data)
  }
}
export function subscribeClinicalChanges(listener:(clear:boolean,scope:'all'|'pdf')=>void) {
  listeners.add(listener);connect()
  return()=>{listeners.delete(listener);if(!listeners.size){channel?.close();channel=undefined}}
}
export function publishClinicalChange(clear=false,scope:'all'|'pdf'='all') {
  const change:Change={type:'clinical-change',clear,scope}
  receive(change)
  // Sending also works on a page with no clinical read subscriptions.
  if(channel)channel.postMessage(change)
  else if(typeof BroadcastChannel!=='undefined') {
    const sender=new BroadcastChannel('isu-clinical-invalidation-v1')
    sender.postMessage(change);sender.close()
  }
}
