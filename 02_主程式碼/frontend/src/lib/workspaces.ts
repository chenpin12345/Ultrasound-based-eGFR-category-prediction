export const workspaces = [
  {id:'research',label:'工作區',href:'/research'},
  {id:'model-center',label:'模型區',href:'/model-center'},
  {id:'clinical',label:'醫師工作區',href:'/clinical/capture'},
] as const
export type WorkspaceId = typeof workspaces[number]['id']
export function workspaceOf(path: string) {
  return workspaces.find(zone => path === '/'+zone.id || path.startsWith('/'+zone.id+'/')) || workspaces[0]
}
export function legacyTarget(path: string, search = '', hash = '') {
  let target = path
  if (['/login','/bootstrap','/select-workspace','/'].includes(path)) target='/research'
  else if (path === '/admin/clinical') target='/model-center/clinical-plans'
  else if (/^\/(research\/)?models(?:\/|$)/.test(path)) target=path.replace(/^\/(research\/)?models/, '/model-center/models')
  else if (/^\/(research\/)?training\/(monitor|[^/]+)$/.test(path)) {
    target=path.replace(/^\/(research\/)?training/, '/model-center/training').replace(/\/monitor$/, '')
  } else if (!path.startsWith('/research/')) target='/research'+path
  return target+search+hash
}
