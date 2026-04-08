import React, { useState, useRef, useCallback } from "react";
import { uploadVideo, pollUntilDone } from "./api";
import VideoPlayer from "./components/VideoPlayer";
import InsightsPanel from "./components/InsightsPanel";
import SearchPanel from "./components/SearchPanel";

export default function App() {
  const [appState, setAppState] = useState("idle"); // idle | uploading | processing | done | error
  const [uploadProgress, setUploadProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [videoUrl, setVideoUrl] = useState(null);
  const playerRef = useRef(null);

  const handleSeek = useCallback((seconds) => {
    if (playerRef.current) {
      playerRef.current.seekTo(seconds);
    }
  }, []);

  const handleFile = useCallback(async (file) => {
    if (!file) return;
    setAppState("uploading");
    setUploadProgress(0);

    // Simulate progress during upload
    const progressInterval = setInterval(() => {
      setUploadProgress((p) => Math.min(p + 10, 90));
    }, 200);

    try {
      const jobId = await uploadVideo(file);
      clearInterval(progressInterval);
      setUploadProgress(100);

      const blobUrl = URL.createObjectURL(file);
      setVideoUrl(blobUrl);
      setAppState("processing");

      pollUntilDone(
        jobId,
        (analysisResult) => {
          setResult(analysisResult);
          setAppState("done");
        },
        () => setAppState("error")
      );
    } catch {
      clearInterval(progressInterval);
      setAppState("error");
    }
  }, []);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleDragOver = (e) => e.preventDefault();

  if (appState === "idle") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-8">
        <Header />
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          className="mt-10 w-full max-w-xl border-2 border-dashed border-brand-border rounded-xl p-16 text-center cursor-pointer hover:border-brand-orange transition-colors bg-brand-surface"
          onClick={() => document.getElementById("file-input").click()}
        >
          <div className="text-5xl mb-4">🎥</div>
          <p className="text-lg font-semibold text-slate-200">
            Drop video footage here
          </p>
          <p className="text-sm text-slate-400 mt-2">
            or click to select a file
          </p>
          <p className="text-xs text-slate-500 mt-4">
            Supports MP4, MOV, AVI, MKV and more
          </p>
          <input
            id="file-input"
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0])}
          />
        </div>
      </div>
    );
  }

  if (appState === "uploading") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-8">
        <Header />
        <div className="mt-10 w-full max-w-md">
          <p className="text-slate-300 mb-3 text-center">Uploading footage...</p>
          <div className="w-full bg-brand-border rounded-full h-2">
            <div
              className="bg-brand-orange h-2 rounded-full transition-all duration-200"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
          <p className="text-xs text-slate-500 mt-2 text-center">
            {uploadProgress}%
          </p>
        </div>
      </div>
    );
  }

  if (appState === "processing") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-8">
        <Header />
        <div className="mt-10 text-center">
          <div className="inline-block w-12 h-12 border-4 border-brand-border border-t-brand-orange rounded-full animate-spin mb-6" />
          <p className="text-lg font-semibold text-slate-200">
            Analyzing footage...
          </p>
          <p className="text-sm text-slate-400 mt-2">
            This takes about 30 seconds
          </p>
        </div>
      </div>
    );
  }

  if (appState === "error") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-8">
        <Header />
        <div className="mt-10 text-center">
          <p className="text-red-400 text-lg mb-4">
            Analysis failed. Please try again.
          </p>
          <button
            onClick={() => setAppState("idle")}
            className="px-6 py-2 bg-brand-orange hover:bg-brand-orange-dark text-white rounded-lg font-semibold transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // done state — 3-panel layout
  return (
    <div className="min-h-screen flex flex-col" style={{ background: "#0f1117" }}>
      <header className="flex items-center justify-between px-6 py-3 border-b border-brand-border">
        <div className="flex items-center gap-3">
          <span className="text-brand-orange font-bold text-xl tracking-wide">
            HALOS
          </span>
          <span className="text-slate-400 text-sm">Video Insight Assistant</span>
        </div>
        <button
          onClick={() => {
            setAppState("idle");
            setResult(null);
            if (videoUrl) URL.revokeObjectURL(videoUrl);
            setVideoUrl(null);
          }}
          className="text-xs text-slate-400 hover:text-slate-200 border border-brand-border px-3 py-1 rounded transition-colors"
        >
          New Analysis
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden p-4 gap-4">
        {/* Left: Video player (60%) */}
        <div className="w-3/5 flex flex-col">
          <VideoPlayer
            ref={playerRef}
            videoUrl={videoUrl}
            events={result?.events || []}
            onSeek={handleSeek}
          />
        </div>

        {/* Right: Insights + Search (40%) */}
        <div className="w-2/5 flex flex-col gap-4 overflow-hidden">
          <InsightsPanel
            summary={result?.summary || ""}
            events={result?.events || []}
            onSeek={handleSeek}
          />
          <SearchPanel events={result?.events || []} onSeek={handleSeek} />
        </div>
      </div>
    </div>
  );
}

function Header() {
  return (
    <div className="text-center">
      <h1 className="text-3xl font-bold tracking-wide">
        <span className="text-brand-orange">HALOS</span>{" "}
        <span className="text-slate-200">Video Insight Assistant</span>
      </h1>
      <p className="text-slate-400 mt-2 text-sm">
        AI-powered forensic analysis for security professionals
      </p>
    </div>
  );
}
