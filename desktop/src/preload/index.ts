import { contextBridge, ipcRenderer } from 'electron'
import type { DesktopBridge, DesktopState } from '../shared/protocol'

const bridge: DesktopBridge = {
  state: () => ipcRenderer.invoke('device:state'),
  pair: (server, code, name) => ipcRenderer.invoke('device:pair', server, code, name),
  policy: change => ipcRenderer.invoke('device:policy', change),
  addRoot: () => ipcRenderer.invoke('device:add-root'),
  removeRoot: root => ipcRenderer.invoke('device:remove-root', root),
  decide: (id, approve) => ipcRenderer.invoke('device:decide', id, approve),
  cancel: id => ipcRenderer.invoke('device:cancel', id),
  unpair: () => ipcRenderer.invoke('device:unpair'),
  updateState: () => ipcRenderer.invoke('device:update-state'),
  checkUpdate: () => ipcRenderer.invoke('device:check-update'),
  installUpdate: () => ipcRenderer.invoke('device:install-update'),
  subscribeUpdate: listener => {
    const handler = (_event: unknown, state: import('../shared/protocol').DesktopUpdateState) => listener(state)
    ipcRenderer.on('device:update-changed', handler)
    return () => ipcRenderer.removeListener('device:update-changed', handler)
  },
  subscribe: listener => {
    const handler = (_event: unknown, state: DesktopState) => listener(state)
    ipcRenderer.on('device:changed', handler)
    return () => ipcRenderer.removeListener('device:changed', handler)
  },
}
contextBridge.exposeInMainWorld('deepclaw', bridge)
