const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  setIgnoreMouseEvents: (v) => ipcRenderer.invoke('set-ignore-mouse-events', !!v),
  focusMainWindow: () => ipcRenderer.invoke('focus-main-window'),
  hideToTray: () => ipcRenderer.invoke('hide-to-tray'),
  showFromTray: () => ipcRenderer.invoke('show-from-tray'),
  openConfigWindow: () => ipcRenderer.invoke('open-config-window')
});

// Listen for faust commands forwarded from the main process
contextBridge.exposeInMainWorld('faust', {
  onCommand: (cb) => {
    // cb will be called with the raw command string from the server
    ipcRenderer.on('faust-command', (evt, cmd) => {
      try {
        cb(cmd);
      } catch (e) {
        console.error('faust.onCommand callback failed', e);
      }
    });
  },
  onPluginInstallResult: (cb) => {
    ipcRenderer.on('plugin-install-result', (_evt, payload) => {
      try {
        cb(payload);
      } catch (e) {
        console.error('faust.onPluginInstallResult callback failed', e);
      }
    });
  }
});

// allow renderer to send logs to main process console
contextBridge.exposeInMainWorld('logToMain', {
  info: (msg) => ipcRenderer.invoke('faust-log', String(msg)).catch(()=>{}),
});
