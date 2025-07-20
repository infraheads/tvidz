import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';

// Mock window.EventSource
class MockEventSource {
  constructor(url) {
    this.url = url;
    this.onmessage = null;
    this.onerror = null;
    setTimeout(() => {
      if (this.onmessage) {
        this.onmessage({ data: JSON.stringify({ status: 'analyzing', progress: 0.5, scene_cuts: [1.23] }) });
        this.onmessage({ data: JSON.stringify({ status: 'done', progress: 1.0, scene_cuts: [1.23, 2.34] }) });
      }
    }, 100);
  }
  close() {}
}
global.EventSource = MockEventSource;

global.fetch = jest.fn((url, opts) => {
  if (url.endsWith('/admin/clear-db')) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'cleared' }) });
  }
  if (url.endsWith('/build-info')) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ inspector: { build_date: '2024-07-01', build_time: '12:00:00', git_commit: 'abc123', service: 'inspector' } }) });
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
});

describe('App', () => {
  it('renders upload button', () => {
    render(<App />);
    expect(screen.getByText(/upload/i)).toBeInTheDocument();
  });

  it('shows progress bar and handles upload', async () => {
    render(<App />);
    const uploadBtn = screen.getByText(/upload/i);
    fireEvent.click(uploadBtn);
    // Simulate file input
    const file = new File(['dummy'], 'test.mp4', { type: 'video/mp4' });
    const input = screen.getByTestId('file-input');
    fireEvent.change(input, { target: { files: [file] } });
    expect(screen.getByText(/uploading/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/analyzing/i)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/analysis complete/i)).toBeInTheDocument());
    expect(screen.getByText(/scene cut timestamps/i)).toBeInTheDocument();
  });

  it('handles SSE error', async () => {
    class ErrorEventSource {
      constructor() { setTimeout(() => this.onerror && this.onerror(), 100); }
      close() {}
    }
    global.EventSource = ErrorEventSource;
    render(<App />);
    const uploadBtn = screen.getByText(/upload/i);
    fireEvent.click(uploadBtn);
    const file = new File(['dummy'], 'test.mp4', { type: 'video/mp4' });
    const input = screen.getByTestId('file-input');
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(screen.getByText(/error contacting inspector/i)).toBeInTheDocument());
  });

  it('cleans the database with button', async () => {
    render(<App />);
    const cleanBtn = screen.getByText(/clean database/i);
    fireEvent.click(cleanBtn);
    await waitFor(() => expect(screen.getByText(/database cleaned successfully/i)).toBeInTheDocument());
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