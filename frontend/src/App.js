import React, { useRef, useState } from "react";
import {
  S3Client,
  PutObjectCommand,
} from "@aws-sdk/client-s3";

const REGION = "us-east-1"; // dummy region for LocalStack
const S3_ENDPOINT = process.env.REACT_APP_S3_ENDPOINT || "http://localhost:4566";
const BUCKET = process.env.REACT_APP_S3_BUCKET || "videos";
const INSPECTOR_URL = "http://localhost:5001";

const s3Client = new S3Client({
  region: REGION,
  endpoint: S3_ENDPOINT,
  forcePathStyle: true,
  credentials: {
    accessKeyId: "test", // LocalStack default
    secretAccessKey: "test",
  },
});

function App() {
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [analysisStatus, setAnalysisStatus] = useState("");
  const [duration, setDuration] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const fileInputRef = useRef();
  const eventSourceRef = useRef();

  const handleUploadClick = () => {
    fileInputRef.current.value = null; // Always reset
    fileInputRef.current.click();
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      uploadFile(file);
    }
  };

  const listenAnalysisSSE = (filename) => {
    setAnalyzing(true);
    setAnalysisStatus("Analyzing...");
    setDuration(null);
    if (eventSourceRef.current) eventSourceRef.current.close();
    const es = new window.EventSource(`${INSPECTOR_URL}/status/stream/${encodeURIComponent(filename)}`);
    eventSourceRef.current = es;
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.status === "done") {
          setAnalysisStatus("Analysis complete!");
          setDuration(data.duration);
          setAnalyzing(false);
          es.close();
        } else if (data.status === "analyzing") {
          setAnalysisStatus("Analyzing...");
        } else if (data.status === "error") {
          setAnalysisStatus("Analysis failed");
          setDuration(null);
          setAnalyzing(false);
          es.close();
        } else {
          setAnalysisStatus("Pending analysis...");
        }
      } catch (err) {
        setAnalysisStatus("Error parsing SSE");
        setAnalyzing(false);
        es.close();
      }
    };
    es.onerror = () => {
      setAnalysisStatus("Error contacting inspector");
      setAnalyzing(false);
      es.close();
    };
  };

  const uploadFile = async (file) => {
    setStatus("Uploading...");
    setProgress(0);
    setAnalysisStatus("");
    setDuration(null);
    setAnalyzing(false);
    try {
      const command = new PutObjectCommand({
        Bucket: BUCKET,
        Key: file.name,
        Body: file,
        ACL: "public-read",
      });
      await s3Client.send(command);
      setStatus("Upload completed!");
      setProgress(100);
      fileInputRef.current.value = null;
      listenAnalysisSSE(file.name);
    } catch (err) {
      console.error("Upload failed:", err);
      setStatus("Upload failed. Check console.");
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      flexDirection: "column",
      justifyContent: "center",
      alignItems: "center",
      background: "#f7f7fa"
    }}>
      <div style={{
        background: "#fff",
        padding: 40,
        borderRadius: 16,
        boxShadow: "0 4px 24px rgba(0,0,0,0.08)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        minWidth: 400
      }}>
        <input
          type="file"
          ref={fileInputRef}
          style={{ display: "none" }}
          onChange={handleFileChange}
        />
        <button
          onClick={handleUploadClick}
          style={{
            fontSize: 24,
            padding: "18px 48px",
            borderRadius: 8,
            background: "#4f8cff",
            color: "#fff",
            border: "none",
            cursor: "pointer",
            fontWeight: 600,
            marginBottom: 24
          }}
        >
          Upload
        </button>
        {/* Upload Progress Bar */}
        <div style={{ width: 320, height: 24, background: "#e0e0e0", borderRadius: 12, overflow: "hidden", marginBottom: 16 }}>
          <div style={{
            width: `${progress}%`,
            height: "100%",
            background: progress === 100 ? "#4caf50" : "#4f8cff",
            transition: "width 0.3s",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontWeight: 600,
            fontSize: 16
          }}>
            {progress > 0 ? `${progress}%` : ""}
          </div>
        </div>
        <p style={{ fontSize: 20, margin: 0 }}>{status}</p>
        {/* Analysis Progress Bar */}
        {progress === 100 && (
          <>
            <div style={{ width: 320, height: 24, background: "#e0e0e0", borderRadius: 12, overflow: "hidden", marginBottom: 16, marginTop: 16 }}>
              <div style={{
                width: analyzing ? "80%" : duration !== null ? "100%" : "0%",
                height: "100%",
                background: analyzing ? "#ff9800" : duration !== null ? "#4caf50" : "#e0e0e0",
                transition: "width 0.3s",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#fff",
                fontWeight: 600,
                fontSize: 16
              }}>
                {analyzing ? analysisStatus : duration !== null ? `Duration: ${duration.toFixed(2)}s` : ""}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default App;
