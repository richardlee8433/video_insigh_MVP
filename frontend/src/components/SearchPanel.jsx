import React, { useState } from "react";
import { EventRow } from "./InsightsPanel";
import { searchEvents } from "../api";

export default function SearchPanel({ events, onSeek, jobIds = [] }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null); // null = not searched yet
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) {
      setResults(null);
      return;
    }
    setLoading(true);
    try {
      const data = await searchEvents(query.trim(), jobIds);
      setResults(data);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  // If no search yet, fall back to showing local events
  const showLocalFallback = results === null;

  return (
    <div
      className="flex flex-col bg-brand-surface rounded-lg border border-brand-border overflow-hidden"
      style={{ maxHeight: "38vh" }}
    >
      <div className="px-4 py-3 border-b border-brand-border">
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              if (!e.target.value.trim()) setResults(null);
            }}
            placeholder="Search across footage..."
            className="flex-1 bg-brand-bg border border-brand-border rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-brand-orange transition-colors"
          />
          <button
            type="submit"
            disabled={loading}
            className="px-3 py-2 bg-brand-orange hover:opacity-80 text-white text-xs font-bold rounded-lg transition-opacity disabled:opacity-40"
          >
            {loading ? "..." : "Search"}
          </button>
        </form>
      </div>

      <div className="overflow-y-auto flex-1">
        {showLocalFallback ? (
          events.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-6 px-4">
              No events available
            </p>
          ) : (
            events.map((event, i) => (
              <EventRow key={i} event={event} onSeek={onSeek} />
            ))
          )
        ) : results.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-6 px-4">
            No matching footage found
          </p>
        ) : (
          results.map((r, i) => (
            <div
              key={i}
              onClick={() => onSeek(r.seconds)}
              className="px-4 py-3 border-b border-brand-border/50 cursor-pointer hover:bg-white/5 transition-colors"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] text-slate-500 font-mono truncate max-w-[60%]">
                  {r.filename}
                </span>
                <span className="text-[10px] font-mono text-brand-orange">
                  {r.timestamp}
                </span>
              </div>
              <p className="text-xs font-semibold text-slate-200 mb-1">{r.label}</p>
              <p className="text-xs text-slate-400 mb-2 line-clamp-2">{r.description}</p>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1 bg-brand-border rounded-full overflow-hidden">
                  <div
                    className="h-full bg-brand-orange rounded-full"
                    style={{ width: `${Math.round(r.score * 100)}%` }}
                  />
                </div>
                <span className="text-[10px] text-slate-500">
                  {Math.round(r.score * 100)}%
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
