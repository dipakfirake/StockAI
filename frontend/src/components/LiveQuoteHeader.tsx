import React, { useState, useEffect } from 'react';
import { Lock } from 'lucide-react';
import { formatINR } from '../utils/formatters';

export interface LiveQuoteHeaderProps {
  symbol: string;
  initialQuote: any;
  info?: any;
  aiScore?: any;
  user?: any;
  onNavigatePricing?: () => void;
  registerTickListener?: (listener: (tick: any) => void) => () => void;
}

export const LiveQuoteHeader = React.memo(function LiveQuoteHeader({
  symbol,
  initialQuote,
  info,
  aiScore,
  user,
  onNavigatePricing,
  registerTickListener,
}: LiveQuoteHeaderProps) {
  const [quote, setQuote] = useState<any>(initialQuote);

  useEffect(() => {
    setQuote(initialQuote);
  }, [initialQuote, symbol]);

  useEffect(() => {
    if (!registerTickListener) return;
    let rafId: number | null = null;
    let pendingTick: any = null;

    const unbind = registerTickListener((tick: any) => {
      pendingTick = tick;
      if (rafId === null) {
        rafId = requestAnimationFrame(() => {
          rafId = null;
          if (!pendingTick) return;
          const t = pendingTick;
          pendingTick = null;
          setQuote((prev: any) => {
            if (!prev) return prev;
            return {
              ...prev,
              price: t.price,
              change: t.change !== undefined ? t.change : prev.change,
              change_pct: t.change_pct !== undefined ? t.change_pct : prev.change_pct,
              volume: t.volume !== undefined ? t.volume : prev.volume,
            };
          });
        });
      }
    });

    return () => {
      unbind();
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
    };
  }, [registerTickListener, symbol]);

  if (!quote) return null;

  return (
    <div className="card" style={{ marginBottom: 16, display: 'flex', gap: 24, alignItems: 'center', flexWrap: 'wrap' }}>
      <div>
        <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{symbol.replace('.NS', '')}</div>
        <div style={{ fontSize: 28, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
          {formatINR(quote.price)}
          {quote.change !== undefined && (
            <span style={{ fontSize: 16, marginLeft: 8, color: quote.change >= 0 ? '#10b981' : '#ef4444' }}>
              {quote.change > 0 ? '+' : ''}{quote.change.toFixed(2)} ({quote.change_pct?.toFixed(2)}%)
            </span>
          )}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        <div><div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>52W High</div><div className="mono">{formatINR(quote['52w_high'])}</div></div>
        <div><div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>52W Low</div><div className="mono">{formatINR(quote['52w_low'])}</div></div>
        <div><div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Volume</div><div className="mono">{quote.volume ? Number(quote.volume).toLocaleString('en-IN') : '—'}</div></div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Market Cap</div>
          <div className="mono">
            {(() => {
              const cap = Number(quote.market_cap || info?.market_cap || 0);
              if (cap > 0) {
                return cap >= 1e7
                  ? `₹${(cap / 1e7).toLocaleString('en-IN', { maximumFractionDigits: 1 })} Cr`
                  : `₹${(cap / 1e9).toFixed(1)} B`;
              }
              return '—';
            })()}
          </div>
        </div>
      </div>
      {/* AI Score Ring */}
      <div id="ai-score-ring" style={{ marginLeft: 'auto', textAlign: 'center', flexShrink: 0 }}>
        {user?.subscription_tier === 'PRO' ? (
          aiScore ? (() => {
            const confidence = Math.round(aiScore.confidence * 100);
            const r = 28;
            const circ = 2 * Math.PI * r;
            const offset = circ - (confidence / 100) * circ;
            const color = aiScore.score === 'BUY' ? '#10b981' : aiScore.score === 'SELL' ? '#ef4444' : '#f59e0b';
            return (
              <div style={{ position: 'relative', width: 76, height: 76, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="76" height="76" style={{ transform: 'rotate(-90deg)', position: 'absolute' }}>
                  <circle cx="38" cy="38" r={r} fill="none" stroke="var(--color-border)" strokeWidth="5" />
                  <circle cx="38" cy="38" r={r} fill="none" stroke={color} strokeWidth="5"
                    strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
                    style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.16,1,0.3,1), stroke 0.4s ease' }}
                  />
                </svg>
                <div style={{ textAlign: 'center', zIndex: 1 }}>
                  <div style={{ fontSize: 15, fontWeight: 800, color }}>{aiScore.score}</div>
                  <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>{confidence}%</div>
                </div>
              </div>
            );
          })()
            : <div style={{ width: 76, height: 76, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div className="skeleton" style={{ width: 60, height: 60, borderRadius: '50%' }} /></div>
        ) : (
          <button onClick={onNavigatePricing} className="badge badge-neutral" style={{ fontSize: 12, padding: '6px 12px', cursor: 'pointer', border: '1px solid var(--color-accent-blue)' }}>
            <Lock size={12} style={{ display: 'inline', marginRight: 4 }}/> PRO
          </button>
        )}
      </div>
    </div>
  );
});

export default LiveQuoteHeader;
