import React from "react";

export default function VersionToggle({ activeVersion, setActiveVersion }) {
  return (
    <div className="flex gap-1 p-1 bg-brand-bg border border-brand-border rounded-lg">
      <button
        onClick={() => setActiveVersion("v1")}
        className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
          activeVersion === "v1"
            ? "bg-slate-600 text-slate-100"
            : "text-slate-400 hover:text-slate-200"
        }`}
      >
        v1.0 &nbsp;Text
      </button>
      <button
        onClick={() => setActiveVersion("v2")}
        className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
          activeVersion === "v2"
            ? "bg-brand-orange text-white"
            : "text-slate-400 hover:text-slate-200"
        }`}
      >
        v2.0 &nbsp;Vision ✦
      </button>
    </div>
  );
}
