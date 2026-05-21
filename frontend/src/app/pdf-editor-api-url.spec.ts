import { editorApiUrl } from './pdf-editor-api-url';

describe('pdf-editor-api-url', () => {
  it('should point local frontend dev servers at the backend', () => {
    const apiUrl = editorApiUrl({ hostname: '127.0.0.1', port: '4201' });

    expect(apiUrl).toBe('http://localhost:8000');
  });

  it('should keep packaged backend pages on same origin', () => {
    const apiUrl = editorApiUrl({ hostname: 'localhost', port: '8000' });

    expect(apiUrl).toBe('');
  });
});
