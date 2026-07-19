/// <reference types="vite/client" />

declare module "*.mp4" {
  const src: string;
  export default src;
}

interface ImportMetaEnv {
  readonly VITE_WS_PATH: string;
  readonly VITE_API_KEY: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** Chromium Document Picture-in-Picture (transcript pop-out). */
interface DocumentPictureInPicture {
  requestWindow(options?: { width?: number; height?: number }): Promise<Window>;
}

interface Window {
  documentPictureInPicture?: DocumentPictureInPicture;
}
