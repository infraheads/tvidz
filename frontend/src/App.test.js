// Mock EventSource, fetch, XMLHttpRequest
class MockEventSource {
  constructor(url) {
    this.url = url;
    this.onmessage = null;
    this.onerror = null;
    setTimeout(() => {
      if (this.onmessage) {
        // Simulate duplicate detection for the relevant test
        this.onmessage({ data: JSON.stringify({ status: 'analyzing', progress: 0.5, scene_cuts: [1.23], duplicates: ['test.mp4'] }) });
        this.onmessage({ data: JSON.stringify({ status: 'done', progress: 1.0, scene_cuts: [1.23, 2.34], duplicates: ['test.mp4'] }) });
      }
    }, 100);
  }
  close() {}
}
global.EventSource = MockEventSource;

global.fetch = jest.fn((url, opts) => {
  if (url.includes('/admin/clear-db')) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'cleared' }) });
  }
  if (url.includes('/build-info')) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ inspector: { build_date: '2024-07-01', build_time: '12:00:00', git_commit: 'abc123', service: 'inspector' } }) });
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
});

class MockXHR {
  constructor() {
    this.upload = {};
    this.headers = {};
    this.status = 200;
    this.statusText = 'OK';
    this.onload = null;
    this.onerror = null;
  }
  open(method, url, async) {}
  setRequestHeader(key, value) {
    this.headers[key] = value;
  }
  send(file) {
    // Simulate upload progress
    if (this.upload && typeof this.upload.onprogress === 'function') {
      this.upload.onprogress({ lengthComputable: true, loaded: 1, total: 1 });
    }
    setTimeout(() => {
      if (this.onload) this.onload();
    }, 10);
  }
}
global.XMLHttpRequest = MockXHR;

import '@testing-library/jest-dom';
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';

describe('App', () => {
  it('renders upload button', () => {
    render(<App />);
    expect(screen.getByText(/upload/i)).toBeInTheDocument();
  });

  it('cleans the database with button', async () => {
    render(<App />);
    const cleanBtn = screen.getByText(/clean database/i);
    fireEvent.click(cleanBtn);
    expect(await screen.findByText(/database cleaned successfully/i)).toBeInTheDocument();
  });

  it('shows build info', async () => {
    render(<App />);
    const toggleBtn = screen.getByText(/show build information/i);
    fireEvent.click(toggleBtn);
    await waitFor(() => expect(screen.getByText(/frontend build/i)).toBeInTheDocument());
    expect(screen.getByText(/inspector build/i)).toBeInTheDocument();
  });

  it('shows duplicate detection UI', async () => {
    render(<App />);
    // Simulate duplicate detection
    fireEvent.click(screen.getByText(/upload/i));
    const file = new File(['dummy'], 'test.mp4', { type: 'video/mp4' });
    const input = screen.getByTestId('file-input');
    fireEvent.change(input, { target: { files: [file] } });
    // Simulate duplicate in SSE
    await waitFor(() => expect(screen.getByText(/duplicate video/i)).toBeInTheDocument());
  });
}); 