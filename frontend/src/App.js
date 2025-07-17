import React, { useRef, useState } from "react";
import {
  S3Client,
  PutObjectCommand,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

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
  const [uploadProgress, setUploadProgress] = useState(0);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [barLabel, setBarLabel] = useState("");
  const [sceneCuts, setSceneCuts] = useState([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [uploadDuration, setUploadDuration] = useState(null);
  const [analysisDuration, setAnalysisDuration] = useState(null);
  const [duplicates, setDuplicates] = useState([]);
  const fileInputRef = useRef();
  const eventSourceRef = useRef();
  const uploadStartRef = useRef(null);
  const analysisStartRef = useRef(null);

  const handleUploadClick = () => {
    fileInputRef.current.value = null; // Always reset
    fileInputRef.current.click();
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      // Always use a unique filename to force S3 event
      const uniqueFile = new File([file], `${Date.now()}-${file.name}`, { type: file.type });
      uploadFile(uniqueFile);
    }
  };

  // Calculate combined progress for the single bar
  const combinedProgress = uploadProgress < 100
    ? uploadProgress * 0.5
    : 50 + analysisProgress * 0.5;

  const listenAnalysisSSE = (filename) => {
    setAnalyzing(true);
    setBarLabel("Analyzing...");
    setSceneCuts([]);
    setAnalysisProgress(0);
    setAnalysisDuration(null);
    analysisStartRef.current = Date.now();
    if (eventSourceRef.current) eventSourceRef.current.close();
    const es = new window.EventSource(`${INSPECTOR_URL}/status/stream/${encodeURIComponent(filename)}`);
    eventSourceRef.current = es;
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.duplicates && Array.isArray(data.duplicates) && data.duplicates.length > 0) {
          setDuplicates(data.duplicates);
        }
        if (data.status === "done") {
          setBarLabel("Analysis complete!");
          setSceneCuts((prev) => {
            // Only append new scene cuts if any
            if (!Array.isArray(data.scene_cuts)) return prev;
            if (data.scene_cuts.length > prev.length) {
              return [...prev, ...data.scene_cuts.slice(prev.length)];
            }
            return prev;
          });
          setAnalysisProgress(100);
          setAnalyzing(false);
          if (analysisStartRef.current) {
            setAnalysisDuration(((Date.now() - analysisStartRef.current) / 1000).toFixed(2));
            analysisStartRef.current = null;
          }
          es.close();
        } else if (data.status === "analyzing") {
          setBarLabel("Analyzing...");
          setSceneCuts((prev) => {
            if (!Array.isArray(data.scene_cuts)) return prev;
            if (data.scene_cuts.length > prev.length) {
              return [...prev, ...data.scene_cuts.slice(prev.length)];
            }
            return prev;
          });
          setAnalysisProgress(
            typeof data.progress === 'number' && isFinite(data.progress)
              ? Math.round(data.progress * 100)
              : 0
          );
        } else if (data.status === "error") {
          setBarLabel("Analysis failed");
          setSceneCuts([]);
          setAnalysisProgress(0);
          setAnalyzing(false);
          if (analysisStartRef.current) {
            setAnalysisDuration(((Date.now() - analysisStartRef.current) / 1000).toFixed(2));
            analysisStartRef.current = null;
          }
          es.close();
        } else {
          setBarLabel("Pending analysis...");
        }
      } catch (err) {
        setBarLabel("Error parsing SSE");
        setAnalyzing(false);
        setSceneCuts([]);
        if (analysisStartRef.current) {
          setAnalysisDuration(((Date.now() - analysisStartRef.current) / 1000).toFixed(2));
          analysisStartRef.current = null;
        }
        es.close();
      }
    };
    es.onerror = () => {
      setBarLabel("Error contacting inspector");
      setAnalyzing(false);
      setSceneCuts([]);
      if (analysisStartRef.current) {
        setAnalysisDuration(((Date.now() - analysisStartRef.current) / 1000).toFixed(2));
        analysisStartRef.current = null;
      }
      es.close();
    };
  };

  const uploadFile = async (file) => {
    setStatus("");
    setUploadProgress(0);
    setAnalysisProgress(0);
    setBarLabel("Uploading...");
    setSceneCuts([]);
    setAnalyzing(false);
    setUploadDuration(null);
    setAnalysisDuration(null);
    uploadStartRef.current = Date.now();
    try {
      // 1. Generate pre-signed PUT URL
      const command = new PutObjectCommand({
        Bucket: BUCKET,
        Key: file.name,
        ACL: "public-read",
        ContentType: file.type || "application/octet-stream",
      });
      const url = await getSignedUrl(s3Client, command, { expiresIn: 300 });

      // 2. Upload using XMLHttpRequest for progress
      await new Promise((resolve, reject) => {
        const xhr = new window.XMLHttpRequest();
        xhr.open("PUT", url, true);
        xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const percent = Math.round((event.loaded / event.total) * 100);
            setUploadProgress(percent);
          }
        };
        xhr.onload = () => {
          if (xhr.status === 200) {
            setBarLabel("Upload completed! Starting analysis...");
            setUploadProgress(100);
            if (uploadStartRef.current) {
              setUploadDuration(((Date.now() - uploadStartRef.current) / 1000).toFixed(2));
              uploadStartRef.current = null;
            }
            fileInputRef.current.value = null;
            listenAnalysisSSE(file.name);
            resolve();
          } else {
            setBarLabel(`Upload failed: ${xhr.statusText}`);
            if (uploadStartRef.current) {
              setUploadDuration(((Date.now() - uploadStartRef.current) / 1000).toFixed(2));
              uploadStartRef.current = null;
            }
            reject(new Error(`Upload failed: ${xhr.statusText}`));
          }
        };
        xhr.onerror = () => {
          setBarLabel("Upload failed. Network error.");
          if (uploadStartRef.current) {
            setUploadDuration(((Date.now() - uploadStartRef.current) / 1000).toFixed(2));
            uploadStartRef.current = null;
          }
          reject(new Error("Upload failed. Network error."));
        };
        xhr.send(file);
      });
    } catch (err) {
      console.error("Upload failed:", err);
      setBarLabel("Upload failed. Check console.");
      if (uploadStartRef.current) {
        setUploadDuration(((Date.now() - uploadStartRef.current) / 1000).toFixed(2));
        uploadStartRef.current = null;
      }
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
        {/* Single Progress Bar for Upload + Analysis */}
        <div style={{ width: 320, height: 24, background: "#e0e0e0", borderRadius: 12, overflow: "hidden", marginBottom: 8 }}>
          <div style={{
            width: `${Math.round(combinedProgress)}%`,
            height: "100%",
            background: uploadProgress === 100 && analysisProgress === 100 ? "#4caf50" : "#4f8cff",
            transition: "width 0.3s",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontWeight: 600,
            fontSize: 16
          }}>
            {barLabel}
          </div>
        </div>
        {/* Durations for upload and analysis */}
        <div style={{ marginBottom: 16, fontSize: 16, color: '#333', minHeight: 24 }}>
          {uploadDuration && <span>Upload duration: {uploadDuration}s</span>}
          {uploadDuration && analysisDuration && <span> &nbsp;|&nbsp; </span>}
          {analysisDuration && <span>Analysis duration: {analysisDuration}s</span>}
        </div>
        {/* Scene Cut Timestamps */}
        {sceneCuts.length > 0 && (
          <div style={{ marginTop: 16, textAlign: "center" }}>
            <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 8 }}>Scene Cut Timestamps:</div>
            <div style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 8,
              justifyContent: "center"
            }}>
              {sceneCuts.map((ts, i) => (
                <span key={i} style={{
                  background: "#f0f0f0",
                  borderRadius: 6,
                  padding: "4px 10px",
                  fontSize: 16,
                  margin: 2
                }}>
                  {Number.isFinite(ts) ? `${ts}s` : 'N/A'}
                </span>
              ))}
            </div>
          </div>
        )}
        {duplicates.length > 0 && (
          <div style={{ marginTop: 24, color: '#b71c1c', fontWeight: 600 }}>
            Duplicate video(s) detected:<br />
            {[...new Set(duplicates)].map((name, i) => (
              <div key={i}>{name}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
