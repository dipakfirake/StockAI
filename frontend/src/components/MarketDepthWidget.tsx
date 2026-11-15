import React, { useEffect, useState, useRef } from 'react';
import { RefreshCw, TrendingUp, TrendingDown, Shield, Zap, X, ShoppingCart } from 'lucide-react';
import { stocksApi } from '../services/api';
import { formatINR, formatNumber2Dec } from '../utils/formatters';

export interface MarketDepthData {
  symbol: string;
  ltp: number;
  previous_close: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  atp: number;
  lower_circuit: number;
  upper_circuit: number;
  spread: number;
  spread_pct: number;
  bids: Array<{ price: number; quantity: number; orders: number }>;
  asks: Array<{ price: number; quantity: number; orders: number }>;
  total_buy_qty: number;
  total_sell_qty: number;
  buy_ratio: number;
  sell_ratio: number;
  data_source: string;
  is_realtime: boolean;
  timestamp: string;
}

interface MarketDepthWidgetProps {
  symbol: string;
  onClose?: () => void;
  onTrade?: (direction: 'BUY' | 'SELL', price?: number) => void;
  compact?: boolean;
}

export default function MarketDepthWidget({ symbol, onClose, onTrade, compact = false }: MarketDepthWidgetProps) {
  const [depth, setDepth] = useState<MarketDepthData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const cleanSymbol = (s: string) => s.replace('.NS', '').replace('.BO', '').replace('^', '').toUpperCase();

  const fetchDepth = async (isManual = false) => {
    if (!symbol) return;
    if (isManual) setRefreshing(true);
    try {
      const res = await stocksApi.getDepth(symbol);
      setDepth(res.data);
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load market depth');
    } finally {
      setLoading(false);
      if (isManual) setTimeout(() => setRefreshing(false), 300);
    }
  };

  useEffect(() => {
    setLoading(true);
    fetchDepth();

    // Poll depth every 2.0s while component is visible (Zero-rate-limit guaranteed by backend cache)
    timerRef.current = window.setInterval(() => {
      fetchDepth();
    }, 2000);

    return () => {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [symbol]);

  if (loading && !depth) {
    return (
      <div style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-muted)' }}>
        <RefreshCw size={24} className="spin" style={{ marginBottom: 12 }} />
        <div>Loading Zerodha Kite Market Depth for {cleanSymbol(symbol)}...</div>
      </div>
    );
  }

  if (error && !depth) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: 'var(--color-sell)' }}>
        <div>{error}</div>
        <button className="btn btn-secondary" onClick={() => fetchDepth(true)} style={{ marginTop: 12 }}>
          Retry
        </button>
      </div>
    );
  }

  if (!depth) return null;

  const isUp = depth.ltp >= depth.previous_close;
  const change = round2(depth.ltp - depth.previous_close);
  const changePct = depth.previous_close > 0 ? round2((change / depth.previous_close) * 100) : 0;
  const totalBidsSum = depth.bids.reduce((s, b) => s + b.quantity, 0);
  const totalAsksSum = depth.asks.reduce((s, a) => s + a.quantity, 0);

  return (
    <div className="kite-market-depth" style={{
      background: 'var(--color-bg-card, #131722)',
      color: 'var(--color-text-primary, #d1d4dc)',
      borderRadius: compact ? 6 : 10,
      border: '1px solid var(--color-border, #2a2e39)',
      padding: compact ? 12 : 16,
      fontFamily: 'Inter, -apple-system, sans-serif',
      fontSize: 12,
      maxWidth: 580,
      width: '100%',
      boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, borderBottom: '1px solid var(--color-border-light, #1e222d)', paddingBottom: 10 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: 0.5 }}>{cleanSymbol(depth.symbol)}</span>
            <span style={{ fontSize: 10, background: '#1e222d', padding: '2px 6px', borderRadius: 4, color: 'var(--color-text-muted, #787b86)' }}>
              NSE
            </span>
            <span style={{ 
              fontSize: 10, 
              padding: '2px 6px', 
              borderRadius: 4, 
              background: depth.is_realtime ? 'rgba(38,166,154,0.15)' : 'rgba(41,98,255,0.15)',
              color: depth.is_realtime ? '#26a69a' : '#2962ff',
              display: 'flex',
              alignItems: 'center',
              gap: 4
            }}>
              {depth.is_realtime ? <Zap size={10} /> : <Shield size={10} />}
              {depth.is_realtime ? 'Live Depth' : 'Simulated L2'}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
            <span className="mono" style={{ fontSize: 18, fontWeight: 700, color: isUp ? '#26a69a' : '#ef5350' }}>
              ₹{formatNumber2Dec(depth.ltp)}
            </span>
            <span style={{ fontSize: 12, fontWeight: 600, color: isUp ? '#26a69a' : '#ef5350', display: 'flex', alignItems: 'center', gap: 2 }}>
              {isUp ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
              {change >= 0 ? '+' : ''}{change} ({changePct >= 0 ? '+' : ''}{changePct}%)
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button 
            onClick={() => fetchDepth(true)} 
            title="Refresh Depth"
            style={{ 
              background: 'none', 
              border: 'none', 
              color: 'var(--color-text-muted, #787b86)', 
              cursor: 'pointer',
              padding: 6,
              borderRadius: 4
            }}
          >
            <RefreshCw size={15} className={refreshing ? 'spin' : ''} />
          </button>
          {onClose && (
            <button 
              onClick={onClose} 
              style={{ background: 'none', border: 'none', color: 'var(--color-text-muted, #787b86)', cursor: 'pointer', padding: 6 }}
            >
              <X size={18} />
            </button>
          )}
        </div>
      </div>

      {/* 5-Level Bid and Ask Tables Side by Side */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
        {/* Bids Table (Blue/Green) */}
        <div>
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: '1fr 1fr 1fr', 
            padding: '4px 6px', 
            background: 'rgba(38,166,154,0.12)', 
            color: '#26a69a', 
            fontWeight: 700, 
            fontSize: 10,
            borderRadius: '4px 4px 0 0',
            letterSpacing: 0.5
          }}>
            <span>BID (₹)</span>
            <span style={{ textAlign: 'right' }}>ORDERS</span>
            <span style={{ textAlign: 'right' }}>QTY</span>
          </div>
          <div style={{ background: 'rgba(38,166,154,0.03)', border: '1px solid rgba(38,166,154,0.1)', borderTop: 'none' }}>
            {depth.bids.map((b, idx) => (
              <div 
                key={idx} 
                onClick={() => onTrade && onTrade('SELL', b.price)}
                title={`Click to Sell against Bid at ₹${b.price}`}
                style={{ 
                  display: 'grid', 
                  gridTemplateColumns: '1fr 1fr 1fr', 
                  padding: '5px 6px',
                  borderBottom: idx < 4 ? '1px solid rgba(255,255,255,0.03)' : 'none',
                  cursor: onTrade ? 'pointer' : 'default',
                  transition: 'background 0.15s ease'
                }}
                className="depth-row-bid"
              >
                <span className="mono" style={{ color: '#26a69a', fontWeight: 600 }}>{formatNumber2Dec(b.price)}</span>
                <span className="mono" style={{ textAlign: 'right', color: 'var(--color-text-muted, #787b86)' }}>{b.orders}</span>
                <span className="mono" style={{ textAlign: 'right', fontWeight: 600 }}>{b.quantity.toLocaleString('en-IN')}</span>
              </div>
            ))}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', padding: '6px', borderTop: '1px solid rgba(38,166,154,0.2)', fontWeight: 700, fontSize: 11 }}>
              <span style={{ color: '#26a69a' }}>Total</span>
              <span></span>
              <span className="mono" style={{ textAlign: 'right', color: '#26a69a' }}>
                {(depth.total_buy_qty || totalBidsSum).toLocaleString('en-IN')}
              </span>
            </div>
          </div>
        </div>

        {/* Asks Table (Red/Orange) */}
        <div>
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: '1fr 1fr 1fr', 
            padding: '4px 6px', 
            background: 'rgba(239,83,80,0.12)', 
            color: '#ef5350', 
            fontWeight: 700, 
            fontSize: 10,
            borderRadius: '4px 4px 0 0',
            letterSpacing: 0.5
          }}>
            <span>OFFER (₹)</span>
            <span style={{ textAlign: 'right' }}>ORDERS</span>
            <span style={{ textAlign: 'right' }}>QTY</span>
          </div>
          <div style={{ background: 'rgba(239,83,80,0.03)', border: '1px solid rgba(239,83,80,0.1)', borderTop: 'none' }}>
            {depth.asks.map((a, idx) => (
              <div 
                key={idx} 
                onClick={() => onTrade && onTrade('BUY', a.price)}
                title={`Click to Buy against Ask at ₹${a.price}`}
                style={{ 
                  display: 'grid', 
                  gridTemplateColumns: '1fr 1fr 1fr', 
                  padding: '5px 6px',
                  borderBottom: idx < 4 ? '1px solid rgba(255,255,255,0.03)' : 'none',
                  cursor: onTrade ? 'pointer' : 'default',
                  transition: 'background 0.15s ease'
                }}
                className="depth-row-ask"
              >
                <span className="mono" style={{ color: '#ef5350', fontWeight: 600 }}>{formatNumber2Dec(a.price)}</span>
                <span className="mono" style={{ textAlign: 'right', color: 'var(--color-text-muted, #787b86)' }}>{a.orders}</span>
                <span className="mono" style={{ textAlign: 'right', fontWeight: 600 }}>{a.quantity.toLocaleString('en-IN')}</span>
              </div>
            ))}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', padding: '6px', borderTop: '1px solid rgba(239,83,80,0.2)', fontWeight: 700, fontSize: 11 }}>
              <span style={{ color: '#ef5350' }}>Total</span>
              <span></span>
              <span className="mono" style={{ textAlign: 'right', color: '#ef5350' }}>
                {(depth.total_sell_qty || totalAsksSum).toLocaleString('en-IN')}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Buyer vs Seller Momentum Ratio Bar */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, fontWeight: 700, marginBottom: 4 }}>
          <span style={{ color: '#26a69a' }}>Buyers: {depth.buy_ratio}%</span>
          <span style={{ color: 'var(--color-text-muted, #787b86)' }}>
            Spread: ₹{depth.spread} ({depth.spread_pct}%)
          </span>
          <span style={{ color: '#ef5350' }}>Sellers: {depth.sell_ratio}%</span>
        </div>
        <div style={{ height: 6, width: '100%', background: '#ef5350', borderRadius: 3, overflow: 'hidden', display: 'flex' }}>
          <div style={{ width: `${depth.buy_ratio}%`, background: '#26a69a', height: '100%' }} />
        </div>
      </div>

      {/* Key Market Statistics Grid */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(4, 1fr)', 
        gap: '6px 12px', 
        padding: '10px 12px', 
        background: 'rgba(255,255,255,0.02)', 
        borderRadius: 6,
        border: '1px solid var(--color-border-light, #1e222d)',
        fontSize: 11
      }}>
        <div>
          <div style={{ color: 'var(--color-text-muted, #787b86)', fontSize: 10 }}>Open</div>
          <div className="mono" style={{ fontWeight: 600 }}>₹{formatNumber2Dec(depth.open)}</div>
        </div>
        <div>
          <div style={{ color: 'var(--color-text-muted, #787b86)', fontSize: 10 }}>High</div>
          <div className="mono" style={{ fontWeight: 600 }}>₹{formatNumber2Dec(depth.high)}</div>
        </div>
        <div>
          <div style={{ color: 'var(--color-text-muted, #787b86)', fontSize: 10 }}>Low</div>
          <div className="mono" style={{ fontWeight: 600 }}>₹{formatNumber2Dec(depth.low)}</div>
        </div>
        <div>
          <div style={{ color: 'var(--color-text-muted, #787b86)', fontSize: 10 }}>Prev. Close</div>
          <div className="mono" style={{ fontWeight: 600 }}>₹{formatNumber2Dec(depth.previous_close)}</div>
        </div>

        <div>
          <div style={{ color: 'var(--color-text-muted, #787b86)', fontSize: 10 }}>Volume</div>
          <div className="mono" style={{ fontWeight: 600 }}>{depth.volume.toLocaleString('en-IN')}</div>
        </div>
        <div>
          <div style={{ color: 'var(--color-text-muted, #787b86)', fontSize: 10 }}>Avg. Price (ATP)</div>
          <div className="mono" style={{ fontWeight: 600 }}>₹{formatNumber2Dec(depth.atp)}</div>
        </div>
        <div>
          <div style={{ color: '#ef5350', fontSize: 10 }}>Lower Circuit</div>
          <div className="mono" style={{ fontWeight: 600, color: '#ef5350' }}>₹{formatNumber2Dec(depth.lower_circuit)}</div>
        </div>
        <div>
          <div style={{ color: '#26a69a', fontSize: 10 }}>Upper Circuit</div>
          <div className="mono" style={{ fontWeight: 600, color: '#26a69a' }}>₹{formatNumber2Dec(depth.upper_circuit)}</div>
        </div>
      </div>

      {/* Quick Trade Buttons */}
      {onTrade && (
        <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
          <button 
            className="btn"
            onClick={() => onTrade('BUY', depth.asks[0]?.price || depth.ltp)}
            style={{ 
              flex: 1, 
              background: '#2962ff', 
              color: 'white', 
              fontWeight: 700, 
              padding: '8px 16px',
              borderRadius: 4,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6
            }}
          >
            <ShoppingCart size={14} /> Buy @ ₹{formatNumber2Dec(depth.asks[0]?.price || depth.ltp)}
          </button>
          <button 
            className="btn"
            onClick={() => onTrade('SELL', depth.bids[0]?.price || depth.ltp)}
            style={{ 
              flex: 1, 
              background: '#ef5350', 
              color: 'white', 
              fontWeight: 700, 
              padding: '8px 16px',
              borderRadius: 4,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6
            }}
          >
            <ShoppingCart size={14} /> Sell @ ₹{formatNumber2Dec(depth.bids[0]?.price || depth.ltp)}
          </button>
        </div>
      )}

      <style>{`
        .depth-row-bid:hover { background: rgba(38,166,154,0.1) !important; }
        .depth-row-ask:hover { background: rgba(239,83,80,0.1) !important; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .spin { animation: spin 1s linear infinite; }
      `}</style>
    </div>
  );
}

function round2(num: number): number {
  return Math.round((num + Number.EPSILON) * 100) / 100;
}
