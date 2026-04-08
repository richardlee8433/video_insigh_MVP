import React from "react";

export default function InsightsPanel({ summary, events, onSeek }) {
  return (
    <div className="flex flex-col bg-brand-surface rounded-lg border border-brand-border overflow-hidden flex-1 min-h-0">
      <div className="px-4 py-3 border-b border-brand-border">
        <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
          AI Summary
        </h2>
      </div>

      <div className="px-4 py-3 border-b border-brand-border">
        <p className="text-sm text-slate-300 leading-relaxed">{summary}</p>
      </div>

      <div className="px-4 py-2 border-b border-brand-border">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          Key Events
        </h3>
      </div>

      <div className="overflow-y-auto flex-1">
        {events.map((event, i) => (
          <EventRow key={i} event={event} onSeek={onSeek} />
        ))}
      </div>
    </div>
  );
}

export function EventRow({ event, onSeek }) {
  return (
    <button
      onClick={() => onSeek(event.seconds)}
      className="w-full text-left px-4 py-3 border-b border-brand-border hover:bg-white/5 transition-colors flex gap-3 items-start group"
    >
      <span className="shrink-0 mt-0.5 px-2 py-0.5 bg-brand-orange text-white text-xs font-mono rounded font-semibold">
        {event.timestamp}
      </span>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-slate-200 group-hover:text-brand-orange transition-colors truncate">
          {event.label}
        </p>
        <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">
          {event.description}
        </p>
      </div>
    </button>
  );
}
