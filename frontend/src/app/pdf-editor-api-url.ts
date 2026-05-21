export interface BrowserLocationParts {
  hostname: string;
  port: string;
}

export function editorApiUrl(location: BrowserLocationParts): string {
  if (!isLocalFrontendHost(location)) {
    return '';
  }
  return 'http://localhost:8000';
}

function isLocalFrontendHost(location: BrowserLocationParts): boolean {
  const hostname = location.hostname.toLowerCase();
  const isLocal = hostname === 'localhost' || hostname === '127.0.0.1';
  return isLocal && location.port !== '' && location.port !== '8000';
}
