import React, {
  useEffect,
  useRef,
  useState,
  forwardRef,
  useImperativeHandle,
} from "react";
import Plyr from "plyr";

const VideoPlayer = forwardRef(function VideoPlayer({ videoUrl, events, onSeek }, ref) {
  const videoEl = useRef(null);
  const plyrInstance = useRef(null);
  const [duration, setDuration] = useState(0);
  const [hoveredEvent, setHoveredEvent] = useState(null);

  useImperativeHandle(ref, () => ({
    seekTo(seconds) {
      if (plyrInstance.current) {
        plyrInstance.current.currentTime = seconds;
        plyrInstance.current.play();
      }
    },
  }));

  useEffect(() => {
    if (!videoEl.current) return;

    plyrInstance.current = new Plyr(videoEl.current, {
      controls: [
        "play-large",
        "play",
        "progress",
        "current-time",
        "mute",
        "volume",
        "fullscreen",
      ],
      tooltips: { controls: true },
    });

    const player = plyrInstance.current;

    const onReady = () => {
      setDuration(player.duration || 0);
    };

    const onDurationChange = () => {
      setDuration(player.duration || 0);
    };

    player.on("ready", onReady);
    player.on("durationchange", onDurationChange);
    player.on("loadedmetadata", onDurationChange);

    return () => {
      player.destroy();
    };
  }, [videoUrl]);

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-lg overflow-hidden bg-black">
        <video ref={videoEl} src={videoUrl} playsInline />
      </div>

      {/* Timeline markers */}
      {duration > 0 && events.length > 0 && (
        <div className="relative h-8 bg-brand-surface rounded-lg border border-brand-border px-2">
          <div className="relative w-full h-full">
            {events.map((event, i) => {
              const pct = Math.min((event.seconds / duration) * 100, 99);
              return (
                <div
                  key={i}
                  className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 group"
                  style={{ left: `${pct}%` }}
                >
                  <button
                    onClick={() => onSeek(event.seconds)}
                    onMouseEnter={() => setHoveredEvent(i)}
                    onMouseLeave={() => setHoveredEvent(null)}
                    className="w-3 h-3 rounded-full bg-brand-orange hover:scale-150 transition-transform border-2 border-brand-bg shadow-lg"
                    aria-label={event.label}
                  />
                  {hoveredEvent === i && (
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-10 whitespace-nowrap">
                      <div className="bg-gray-900 text-xs text-slate-200 px-2 py-1 rounded shadow-xl border border-brand-border">
                        <span className="text-brand-orange font-mono mr-1">
                          {event.timestamp}
                        </span>
                        {event.label}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {duration > 0 && events.length > 0 && (
        <p className="text-xs text-slate-500 text-center">
          {events.length} event{events.length !== 1 ? "s" : ""} detected — click
          a marker to jump
        </p>
      )}
    </div>
  );
});

export default VideoPlayer;
