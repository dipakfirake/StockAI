import { Play, Pause, SkipForward, FastForward, X } from 'lucide-react';
import './ChartReplayControls.css';

interface ChartReplayControlsProps {
  isReplaying: boolean;
  onToggleReplay: () => void;
  onStep: () => void;
  speed: number;
  onSpeedChange: (s: number) => void;
  onClose: () => void;
}

export default function ChartReplayControls({
  isReplaying,
  onToggleReplay,
  onStep,
  speed,
  onSpeedChange,
  onClose
}: ChartReplayControlsProps) {
  return (
    <div className="replay-controls-panel">
      <div className="replay-header">
        <span className="replay-title">Bar Replay</span>
        <button className="icon-btn" onClick={onClose}><X size={14} /></button>
      </div>
      <div className="replay-actions">
        <button className="replay-btn" onClick={onToggleReplay} title={isReplaying ? "Pause" : "Play"}>
          {isReplaying ? <Pause size={18} /> : <Play size={18} fill="currentColor" />}
        </button>
        <button className="replay-btn" onClick={onStep} disabled={isReplaying} title="Forward 1 Bar">
          <SkipForward size={18} />
        </button>
        <div className="speed-control">
          <FastForward size={14} className="text-muted" />
          <select 
            value={speed} 
            onChange={(e) => onSpeedChange(Number(e.target.value))}
            className="speed-select"
          >
            <option value={1000}>1x</option>
            <option value={500}>2x</option>
            <option value={200}>5x</option>
            <option value={100}>10x</option>
          </select>
        </div>
      </div>
    </div>
  );
}
