import React, { useState, useRef, useEffect, useCallback } from "react";
import { analyzeLiveFrame } from "../api";

export default function LiveMonitor() {
  const [isActive, setIsActive] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [currentAlertStatus, setCurrentAlertStatus] = useState("NORMAL"); // NORMAL | CAUTION | ALERT
  const [sessionId, setSessionId] = useState(null);
  
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const prevFrameData = useRef(null);
  const samplingInterval = useRef(null);

  const startLive = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        setIsActive(true);
        // Reset session
        setAlerts([]);
        setCurrentAlertStatus("NORMAL");
        setSessionId(`live_${new Date().getTime()}`);
      }
    } catch (err) {
      console.error("Error accessing webcam:", err);
      alert("Could not access webcam. Please ensure permissions are granted.");
    }
  };

  const stopLive = () => {
    if (videoRef.current && videoRef.current.srcObject) {
      const tracks = videoRef.current.srcObject.getTracks();
      tracks.forEach(track => track.stop());
      videoRef.current.srcObject = null;
    }
    setIsActive(false);
    if (samplingInterval.current) {
      clearInterval(samplingInterval.current);
    }
  };

  const calculatePixelDiff = (currentData, previousData) => {
    if (!previousData) return 1.0; // 100% diff if no previous frame
    let diff = 0;
    const data1 = currentData.data;
    const data2 = previousData.data;
    for (let i = 0; i < data1.length; i += 4) {
      // Simple luminosity diff
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
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    
    // Set canvas size to video size
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const currentFrameData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const diff = calculatePixelDiff(currentFrameData, prevFrameData.current);
    
    // Requirement: only send if pixel change > 15%
    if (diff > 0.15) {
      prevFrameData.current = currentFrameData;
      
      canvas.toBlob(async (blob) => {
        if (!blob) return;
        
        // Hash frame blob using SubtleCrypto
        const arrayBuffer = await blob.arrayBuffer();
        const hashBuffer = await crypto.subtle.digest("SHA-256", arrayBuffer);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map(b => b.toString(16).padStart(2, "0")).join("");

        // Convert to base64
        const reader = new FileReader();
        reader.readAsDataURL(blob);
        reader.onloadend = async () => {
          const base64data = reader.result.split(',')[1];
          try {
            const result = await analyzeLiveFrame(base64data, hashHex, sessionId);
            const newAlert = {
              ...result,
              id: Date.now(),
              snapshot: reader.result // Save snapshot for demo
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
  }, [isActive, sessionId]);

  useEffect(() => {
    if (isActive) {
      samplingInterval.current = setInterval(captureFrame, 5000);
    } else {
      if (samplingInterval.current) clearInterval(samplingInterval.current);
    }
    return () => {
      if (samplingInterval.current) clearInterval(samplingInterval.current);
    };
  }, [isActive, captureFrame]);

  const getLabelColor = (label) => {
    const l = label.toUpperCase();
    if (l.includes("ALERT")) return "bg-red-500 text-white";
    if (l.includes("CAUTION")) return "bg-amber-500 text-black";
    return "bg-green-500 text-white";
  };

  return (
    <div className="flex flex-1 overflow-hidden p-4 gap-4 bg-[#0f1117]">
      {/* Left Panel: Webcam Feed */}
      <div className="w-3/5 flex flex-col gap-3 relative">
        <div className={`relative flex-1 bg-black rounded-xl overflow-hidden border-4 transition-all duration-500 ${currentAlertStatus === "ALERT" ? "border-red-600 animate-pulse" : "border-brand-border"}`}>
          {isActive && (
            <div className="absolute top-4 left-4 z-10 flex items-center gap-2">
              <span className="flex h-3 w-3 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
              </span>
              <span className="bg-red-600 text-white text-[10px] font-bold px-2 py-0.5 rounded shadow-lg">LIVE</span>
            </div>
          )}
          <video 
            ref={videoRef} 
            autoPlay 
            muted 
            playsInline 
            className="w-full h-full object-cover"
          />
          {!isActive && (
            <div className="absolute inset-0 flex items-center justify-center text-slate-500 flex-col gap-4">
              <div className="text-6xl opacity-20">📹</div>
              <p className="text-sm">Camera inactive</p>
            </div>
          )}
          <div className="absolute bottom-4 right-4 text-[10px] text-slate-400 bg-black/60 px-3 py-1 rounded backdrop-blur-sm">
            For demo: using webcam. Production connects to CCTV m3u8 streams.
          </div>
        </div>
        
        <div className="flex justify-center">
          {!isActive ? (
            <button
              onClick={startLive}
              className="px-8 py-3 bg-brand-orange hover:bg-brand-orange-dark text-white rounded-full font-bold transition-all transform hover:scale-105 shadow-xl flex items-center gap-2"
            >
              <span className="text-xl">●</span> Start Live Monitoring
            </button>
          ) : (
            <button
              onClick={stopLive}
              className="px-8 py-3 bg-slate-700 hover:bg-slate-600 text-white rounded-full font-bold transition-all transform hover:scale-105 flex items-center gap-2"
            >
              <span className="text-xl">■</span> Stop Monitoring
            </button>
          )}
        </div>
      </div>

      {/* Right Panel: Live Alerts */}
      <div className="w-2/5 flex flex-col gap-4 bg-brand-surface border border-brand-border rounded-xl p-4 overflow-hidden">
        <div className="flex items-center justify-between border-b border-brand-border pb-3">
          <h2 className="text-lg font-bold text-slate-200">Proactive Alerts</h2>
          <span className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">HALOS v4.0 Engine</span>
        </div>
        
        <div className="flex-1 overflow-y-auto space-y-3 pr-2 custom-scrollbar">
          {alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-600 opacity-50">
              <div className="text-4xl mb-2">🛡️</div>
              <p className="text-sm italic">Waiting for detection events...</p>
            </div>
          ) : (
            alerts.map((alert) => (
              <div 
                key={alert.id} 
                className="bg-brand-border/30 border border-brand-border rounded-lg p-3 hover:bg-brand-border/50 transition-colors cursor-pointer"
                onClick={() => {
                  // Logic to "save snapshot to session" - here we just show a toast or log
                  console.log("Snapshot saved to forensic vault:", alert.hash);
                }}
              >
                <div className="flex items-start justify-between mb-2">
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${getLabelColor(alert.label)}`}>
                    {alert.label}
                  </span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {new Date(alert.timestamp).toLocaleTimeString()}
                  </span>
                </div>
                <p className="text-sm text-slate-300 leading-relaxed mb-3">
                  {alert.description}
                </p>
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
