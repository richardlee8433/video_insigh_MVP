import React, { useState, useRef, useEffect, useCallback } from "react";
import Hls from "hls.js";
import { analyzeLiveFrame } from "../api";

export default function LiveMonitor() {
  const [isActive, setIsActive] = useState(false);
  const [streamUrl, setStreamUrl] = useState("https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8");
  const [alerts, setAlerts] = useState([]);
  const [currentAlertStatus, setCurrentAlertStatus] = useState("NORMAL"); // NORMAL | CAUTION | ALERT
  const [sessionId, setSessionId] = useState(null);
  const [connStatus, setConnStatus] = useState("Disconnected"); // Disconnected | Connected | Error | Stalled
  const [errorMessage, setErrorMessage] = useState("");
  const [isVideoReady, setIsVideoReady] = useState(false);
  const [showForcePlay, setShowForcePlay] = useState(false);
  
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const hlsRef = useRef(null);
  const prevFrameData = useRef(null);
  const samplingInterval = useRef(null);
  const stallTimer = useRef(null);
  const forcePlayTimer = useRef(null);
  const hasTaintedCanvasWarned = useRef(false);
  const alertsEndRef = useRef(null);

  const destroyHls = () => {
    if (samplingInterval.current) {
      clearInterval(samplingInterval.current);
      samplingInterval.current = null;
    }
    if (hlsRef.current) {
      hlsRef.current.detachMedia();
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
    if (stallTimer.current) {
      clearTimeout(stallTimer.current);
      stallTimer.current = null;
    }
    if (forcePlayTimer.current) {
      clearTimeout(forcePlayTimer.current);
      forcePlayTimer.current = null;
    }
    setIsVideoReady(false);
    setShowForcePlay(false);
    hasTaintedCanvasWarned.current = false;
  };

  const handleMetadata = useCallback(() => {
    if (videoRef.current && videoRef.current.videoWidth > 0) {
      console.log("Metadata loaded, stream dimensions confirmed:", videoRef.current.videoWidth, "x", videoRef.current.videoHeight);
      setIsVideoReady(true);
      setShowForcePlay(false);
      if (forcePlayTimer.current) {
        clearTimeout(forcePlayTimer.current);
        forcePlayTimer.current = null;
      }
    }
  }, []);

  const connectStream = useCallback(() => {
    if (!streamUrl) {
      setErrorMessage("Please enter a stream URL");
      setConnStatus("Error");
      return;
    }

    setErrorMessage("");
    setConnStatus("Connecting...");
    destroyHls();

    if (Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true,
      });
      hlsRef.current = hls;
      
      hls.loadSource(streamUrl);
      hls.attachMedia(videoRef.current);

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setConnStatus("Connected");
        setIsActive(true);
        setSessionId(`live_${new Date().getTime()}`);
        
        // Explicitly start loading after manifest is parsed
        hls.startLoad();

        const playPromise = videoRef.current.play();
        if (playPromise !== undefined) {
          playPromise.catch(error => {
            if (error.name === "AbortError") {
              console.log("Playback interrupted by new load request (AbortError).");
            } else {
              console.error("Auto-play failed:", error);
            }
          });
        }

        // Start force play timer for dev mode
        if (import.meta.env.DEV) {
          forcePlayTimer.current = setTimeout(() => {
            if (!isVideoReady) setShowForcePlay(true);
          }, 5000);
        }
      });

      hls.on(Hls.Events.ERROR, (event, data) => {
        console.error("HLS Error:", data);
        
        if (data.details === Hls.ErrorDetails.BUFFER_STALLED_ERROR) {
          // Non-fatal, attempt recovery
          console.log("Buffer stalled, attempting recovery...");
          hls.recoverMediaError();
          return;
        }

        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              setErrorMessage("Stream Offline — Check URL");
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              setErrorMessage("Stream Unstable — Reconnecting...");
              hls.recoverMediaError();
              break;
            default:
              setErrorMessage("Fatal Playback Error");
              destroyHls();
              break;
          }
          setConnStatus("Error");
        }
      });

      hls.on(Hls.Events.BUFFER_STALLED, () => {
        setConnStatus("Stalled");
        if (!stallTimer.current) {
          stallTimer.current = setTimeout(() => {
            setErrorMessage("Stream Unstable — Reconnecting...");
          }, 10000);
        }
      });

      hls.on(Hls.Events.BUFFER_APPENDED, () => {
        if (stallTimer.current) {
          clearTimeout(stallTimer.current);
          stallTimer.current = null;
        }
        if (connStatus === "Stalled") setConnStatus("Connected");
      });

    } else if (videoRef.current.canPlayType("application/vnd.apple.mpegurl")) {
      // Native Safari support
      videoRef.current.src = streamUrl;
      
      // Native metadata listener is handled by the useEffect event registration
      
      const playPromise = videoRef.current.play();
      if (playPromise !== undefined) {
        playPromise.catch(error => {
          if (error.name === "AbortError") {
            console.log("Playback interrupted by new load request (AbortError).");
          } else {
            console.error("Native play failed:", error);
          }
        });
      }
      
      videoRef.current.addEventListener("error", () => {
        setErrorMessage("Stream Offline — Check URL");
        setConnStatus("Error");
      });
    } else {
      setErrorMessage("CORS blocked or Browser not supported. In production, use a proxy server or ensure CCTV system allows cross-origin access.");
      setConnStatus("Error");
    }
  }, [streamUrl, isVideoReady]);

  // HLS Initialization Effect - refined dependencies
  useEffect(() => {
    if (isActive) {
      connectStream();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamUrl]); // streamUrl as the only dependency for HLS initialization logic

  // Metadata Event Listener Effect
  useEffect(() => {
    const video = videoRef.current;
    if (video) {
      video.addEventListener("loadedmetadata", handleMetadata);
    }
    return () => {
      if (video) video.removeEventListener("loadedmetadata", handleMetadata);
    };
  }, [handleMetadata]);

  const stopLive = () => {
    destroyHls();
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.src = "";
    }
    setIsActive(false);
    setConnStatus("Disconnected");
  };

  const calculatePixelDiff = (currentData, previousData) => {
    if (!previousData) return 1.0; 
    let diff = 0;
    const data1 = currentData.data;
    const data2 = previousData.data;
    for (let i = 0; i < data1.length; i += 4) {
      const avg1 = (data1[i] + data1[i+1] + data1[i+2]) / 3;
      const avg2 = (data2[i] + data2[i+1] + data2[i+2]) / 3;
      if (Math.abs(avg1 - avg2) > 30) {
        diff++;
      }
    }
    return diff / (data1.length / 4);
  };

  const captureFrame = useCallback(async () => {
    if (!videoRef.current || !canvasRef.current || !isActive) return;

    const video = videoRef.current;
    
    // Metadata Guard: Verify dimensions are valid before sampling
    if (video.videoWidth === 0 || video.videoHeight === 0) {
      if (isVideoReady) setIsVideoReady(false);
      return;
    }
    
    if (!isVideoReady) setIsVideoReady(true);

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    let shouldAnalyze = true;
    try {
      const currentFrameData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const diff = calculatePixelDiff(currentFrameData, prevFrameData.current);
      if (diff < 0.15) {
        shouldAnalyze = false;
        console.log("Static scene (diff < 15%), skipping analysis");
      } else {
        prevFrameData.current = currentFrameData;
      }
    } catch (err) {
      if (!hasTaintedCanvasWarned.current) {
        console.warn("Canvas tainted or getImageData failed, sending frame anyway:", err);
        hasTaintedCanvasWarned.current = true;
      }
      // Requirement: skip pixel diff silently on tainted canvas, continue analysis
    }
    
    if (shouldAnalyze) {
      canvas.toBlob(async (blob) => {
        if (!blob) return;
        
        const arrayBuffer = await blob.arrayBuffer();
        const hashBuffer = await crypto.subtle.digest("SHA-256", arrayBuffer);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map(b => b.toString(16).padStart(2, "0")).join("");

        const reader = new FileReader();
        reader.readAsDataURL(blob);
        reader.onloadend = async () => {
          const base64data = reader.result.split(',')[1];
          try {
            const result = await analyzeLiveFrame(base64data, hashHex);
            const newAlert = {
              ...result,
              id: Date.now(),
              hash: hashHex
            };
            setAlerts(prev => [newAlert, ...prev]);
            
            const labelStr = result.label.toUpperCase();
            if (labelStr.includes("ALERT")) {
              setCurrentAlertStatus("ALERT");
            } else if (labelStr.includes("CAUTION")) {
              setCurrentAlertStatus("CAUTION");
            } else {
              setCurrentAlertStatus("NORMAL");
            }
          } catch (err) {
            console.error("Live analysis error:", err);
          }
        };
      }, "image/jpeg", 0.7);
    }
  }, [isActive, sessionId, isVideoReady]);

  useEffect(() => {
    if (isActive) {
      samplingInterval.current = setInterval(captureFrame, 5000);
    } else {
      if (samplingInterval.current) {
        clearInterval(samplingInterval.current);
        samplingInterval.current = null;
      }
    }
    return () => {
      if (samplingInterval.current) {
        clearInterval(samplingInterval.current);
        samplingInterval.current = null;
      }
    };
  }, [isActive, captureFrame]);

  useEffect(() => {
    alertsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [alerts]);

  const getLabelColor = (label) => {
    const l = label.toUpperCase();
    if (l.includes("ALERT")) return "bg-red-500 text-white";
    if (l.includes("CAUTION")) return "bg-amber-500 text-black";
    return "bg-green-500 text-white";
  };

  const getTriggerBadgeColor = (trigger) => {
    switch (trigger) {
      case "violence": return "bg-red-600 text-white";
      case "crowd_density": return "bg-amber-500 text-black";
      case "unauthorized_access": return "bg-orange-500 text-white";
      case "suspect_object": return "bg-purple-600 text-white";
      default: return "bg-slate-600 text-slate-300";
    }
  };

  return (
    <div className="flex flex-1 overflow-hidden p-4 gap-4 bg-[#0f1117]">
      {/* Left Panel: Stream Feed */}
      <div className="w-3/5 flex flex-col gap-4 relative">
        <div className={`relative flex-1 bg-black rounded-xl overflow-hidden border-4 transition-all duration-500 ${currentAlertStatus === "ALERT" ? "border-red-600 animate-pulse" : "border-brand-border"}`}>
          {isActive && (
            <div className="absolute top-4 left-4 z-10 flex items-center gap-2">
              <span className="flex h-3 w-3 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
              </span>
              <span className="bg-red-600 text-white text-[10px] font-bold px-2 py-0.5 rounded shadow-lg">LIVE</span>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${connStatus === 'Connected' ? 'bg-green-600 text-white' : 'bg-slate-600 text-slate-300'}`}>
                {connStatus.toUpperCase()}
              </span>
            </div>
          )}
          
          <video 
            ref={videoRef} 
            muted 
            playsInline 
            crossOrigin="anonymous"
            className="w-full h-full object-contain"
          />

          {isActive && !isVideoReady && !errorMessage && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/60 backdrop-blur-sm">
              <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 border-4 border-brand-orange border-t-transparent rounded-full animate-spin"></div>
                <p className="text-white font-bold text-sm tracking-widest uppercase">Buffering Stream...</p>
                {import.meta.env.DEV && showForcePlay && (
                  <button
                    onClick={() => {
                      if (videoRef.current) videoRef.current.play().catch(e => console.error("Force play failed:", e));
                    }}
                    className="mt-2 px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] rounded border border-slate-700 transition-colors uppercase font-bold"
                  >
                    Force Play (Dev Only)
                  </button>
                )}
              </div>
            </div>
          )}

          {errorMessage && (
            <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/80 backdrop-blur-sm p-8 text-center">
              <div className="max-w-md">
                <div className="text-4xl mb-4 text-red-500">⚠️</div>
                <h3 className="text-xl font-bold text-white mb-2">Connection Issue</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{errorMessage}</p>
                <button 
                  onClick={connectStream}
                  className="mt-6 px-6 py-2 bg-brand-orange text-white rounded-lg text-sm font-bold"
                >
                  Retry Connection
                </button>
              </div>
            </div>
          )}

          {!isActive && !errorMessage && (
            <div className="absolute inset-0 flex items-center justify-center text-slate-500 flex-col gap-4">
              <div className="text-6xl opacity-20">📡</div>
              <p className="text-sm">Stream Disconnected</p>
            </div>
          )}
          
          <div className="absolute bottom-4 right-4 text-[10px] text-slate-400 bg-black/60 px-3 py-1 rounded backdrop-blur-sm">
            CCTV m3u8 (HLS) Interface v4.0
          </div>
        </div>
        
        {/* Stream Controller */}
        <div className="bg-brand-surface border border-brand-border rounded-xl p-4 flex gap-4 items-center">
          <div className="flex-1">
            <label className="text-[10px] text-slate-500 font-bold uppercase mb-1 block">m3u8 Stream URL</label>
            <input
              type="text"
              value={streamUrl}
              onChange={(e) => setStreamUrl(e.target.value)}
              placeholder="https://..."
              className="w-full bg-black border border-brand-border rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-brand-orange"
            />
          </div>
          <div className="flex gap-2 self-end">
            {!isActive ? (
              <button
                onClick={connectStream}
                className="px-6 py-2 bg-brand-orange hover:bg-brand-orange-dark text-white rounded font-bold transition-all text-sm flex items-center gap-2"
              >
                Connect Stream
              </button>
            ) : (
              <button
                onClick={stopLive}
                className="px-6 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded font-bold transition-all text-sm flex items-center gap-2"
              >
                Disconnect
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Right Panel: Live Alerts */}
      <div className="w-2/5 flex flex-col gap-4 bg-brand-surface border border-brand-border rounded-xl p-4 overflow-hidden">
        <div className="flex items-center justify-between border-b border-brand-border pb-3">
          <h2 className="text-lg font-bold text-slate-200">Proactive Alerts</h2>
          <span className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">Forensics Engine</span>
        </div>
        
        <div className="overflow-y-auto max-h-[calc(100vh-120px)] scroll-smooth space-y-3 pr-2 custom-scrollbar">
          {alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-600 opacity-50">
              <div className="text-4xl mb-2">🛡️</div>
              <p className="text-sm italic">Waiting for detection events...</p>
            </div>
          ) : (
            alerts.map((alert) => (
              <div
                key={alert.id}
                className={`bg-brand-border/30 border border-brand-border rounded-lg p-3 hover:bg-brand-border/50 transition-colors cursor-pointer ${alert.label.includes('ALERT') ? 'border-red-900/50' : ''}`}
                onClick={() => console.log("Snapshot saved to forensic vault:", alert.hash)}
              >
                <div className="flex items-start justify-between mb-1">
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${getLabelColor(alert.label)}`}>
                    {alert.label}
                  </span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {new Date(alert.timestamp).toLocaleTimeString()}
                  </span>
                </div>
                {alert.primary_trigger && alert.primary_trigger !== "none" && (
                  <div className="mb-2">
                    <span className={`text-[9px] font-bold px-2 py-0.5 rounded ${getTriggerBadgeColor(alert.primary_trigger)}`}>
                      {alert.primary_trigger.replace("_", " ")}
                    </span>
                  </div>
                )}
                <p className="text-sm text-slate-300 leading-relaxed mb-2">
                  {alert.description}
                </p>
                {alert.people_count > 0 && (
                  <p className="text-[10px] text-slate-400 mb-2">
                    👥 Estimated: {alert.people_count} people
                  </p>
                )}
                <div className="flex items-center justify-between mt-2 pt-2 border-t border-brand-border/50">
                  <span className="text-[9px] text-slate-500 font-mono">
                    SHA256: {alert.hash.substring(0, 16)}...
                  </span>
                  <span className="text-[10px] text-brand-orange font-bold uppercase tracking-tighter">
                    {Math.round(alert.confidence * 100)}% Conf.
                  </span>
                </div>
              </div>
            ))
          )}
          <div ref={alertsEndRef} />
        </div>
      </div>
      
      <canvas ref={canvasRef} style={{ display: "none" }} />
      
      <style>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #334155;
          border-radius: 10px;
        }
      `}</style>
    </div>
  );
}
