export type UpdaterStatus =
  | 'idle'
  | 'disabled'
  | 'checking'
  | 'available'
  | 'not-available'
  | 'downloading'
  | 'downloaded'
  | 'installing'
  | 'error';

export type UpdaterErrorCode =
  | 'NETWORK_ERROR'
  | 'SIGNATURE_ERROR'
  | 'UNAVAILABLE'
  | 'UPDATER_ERROR';

export interface UpdaterProgress {
  percent: number;
  bytesPerSecond: number;
  transferred: number;
  total: number;
}

export interface UpdaterStatusPayload {
  status: UpdaterStatus;
  version?: string;
  releaseDate?: string;
  progress?: UpdaterProgress;
  error?: string;
  errorCode?: UpdaterErrorCode;
}

export interface UpdaterActionResult {
  ok: boolean;
  status: UpdaterStatus;
  version?: string;
  error?: string;
  errorCode?: UpdaterErrorCode;
}

export interface OmniUpdaterBridge {
  checkForUpdates: () => Promise<UpdaterActionResult>;
  downloadUpdate: () => Promise<UpdaterActionResult>;
  installUpdate: () => Promise<UpdaterActionResult>;
  onStatus: (listener: (payload: UpdaterStatusPayload) => void) => () => void;
}

declare global {
  interface Window {
    omniUpdater?: OmniUpdaterBridge;
  }
}
