import React, { useState, useMemo } from "react";
import { EventRow } from "./InsightsPanel";

export default function SearchPanel({ events, onSeek }) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (!query.trim()) return events;
    const q = query.toLowerCase();
    return events.filter(
      (e) =>
        e.label.toLowerCase().includes(q) ||
        e.description.toLowerCase().includes(q)
    );
  }, [query, events]);

  return (
    <div className="flex flex-col bg-brand-surface rounded-lg border border-brand-border overflow-hidden" style={{ maxHeight: "38vh" }}>
      <div className="px-4 py-3 border-b border-brand-border">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search footage..."
          className="w-full bg-brand-bg border border-brand-border rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-brand-orange transition-colors"
        />
      </div>

      <div className="overflow-y-auto flex-1">
        {filtered.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-6 px-4">
            No events found for this query
          </p>
        ) : (
          filtered.map((event, i) => (
            <EventRow key={i} event={event} onSeek={onSeek} />
          ))
        )}
      </div>
    </div>
  );
}
