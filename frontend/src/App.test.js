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
    // Progress bar should show "Uploading..."
    expect(screen.getByText(/uploading/i)).toBeInTheDocument();
    // Wait for analysis phase
    await waitFor(() => expect(screen.getByText(/analyzing/i)).toBeInTheDocument());
    // Wait for analysis complete
    await waitFor(() => expect(screen.getByText(/analysis complete/i)).toBeInTheDocument());
    // Scene cuts should appear
    expect(screen.getByText(/scene cut timestamps/i)).toBeInTheDocument();
  });

  it('handles SSE error', async () => {
    // Override EventSource to trigger error
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
}); 