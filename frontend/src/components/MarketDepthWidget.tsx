import React, { useEffect, useState, useRef } from 'react';
import { RefreshCw, TrendingUp, TrendingDown, Shield, Zap, X, ShoppingCart } from 'lucide-react';
import { stocksApi } from '../services/api';
import { formatNumber2Dec } from '../utils/formatters';

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
  inline?: boolean;
}

export default function MarketDepthWidget({
  symbol,
  onClose,
  onTrade,
  compact = false,
  inline = false,
}: MarketDepthWidgetProps) {
  const [depth, setDepth] = useState<MarketDepthData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const cleanSymbol = (s: string) =>
    s.replace('.NS', '').replace('.BO', '').replace('^', '').toUpperCase();

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

  // Ensure exactly 5 rows for bids and 5 rows for asks (pad with 0s if empty, matching Kite screenshot)
  const bids = [...(depth.bids || [])];
  while (bids.length < 5) {
    bids.push({ price: 0.0, orders: 0, quantity: 0 });
  }

  const asks = [...(depth.asks || [])];
  while (asks.length < 5) {
    asks.push({ price: 0.0, orders: 0, quantity: 0 });
  }

  const totalBidsSum = depth.total_buy_qty || bids.reduce((s, b) => s + b.quantity, 0);
  const totalAsksSum = depth.total_sell_qty || asks.reduce((s, a) => s + a.quantity, 0);

  return (
    <div
      className="kite-market-depth"
      style={{
        background: inline ? 'transparent' : 'var(--color-bg-card, #131722)',
        color: 'var(--color-text-primary, #d1d4dc)',
        borderRadius: compact ? 6 : 10,
        border: inline ? 'none' : '1px solid var(--color-border, #2a2e39)',
        padding: compact ? 12 : inline ? 0 : 16,
        fontFamily: 'Inter, -apple-system, sans-serif',
        fontSize: 12,
        maxWidth: inline ? '100%' : 620,
        width: '100%',
        boxShadow: inline ? 'none' : '0 8px 24px rgba(0,0,0,0.35)',
      }}
    >
      {/* Header (Only if not inline or if explicitly needed) */}
      {!inline && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 12,
            borderBottom: '1px solid var(--color-border-light, #1e222d)',
            paddingBottom: 10,
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: 0.5 }}>
                {cleanSymbol(depth.symbol)}
              </span>
              <span
                style={{
                  fontSize: 10,
                  background: '#1e222d',
                  padding: '2px 6px',
                  borderRadius: 4,
                  color: 'var(--color-text-muted, #787b86)',
                }}
              >
                NSE
              </span>
              <span
                style={{
                  fontSize: 10,
                  padding: '2px 6px',
                  borderRadius: 4,
                  background: depth.is_realtime
                    ? 'rgba(38,166,154,0.15)'
                    : 'rgba(41,98,255,0.15)',
                  color: depth.is_realtime ? '#26a69a' : '#2962ff',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                }}
              >
                {depth.is_realtime ? <Zap size={10} /> : <Shield size={10} />}
                {depth.is_realtime ? 'Live Depth' : 'Simulated L2'}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
              <span
                className="mono"
                style={{ fontSize: 18, fontWeight: 700, color: isUp ? '#26a69a' : '#ef5350' }}
              >
                ₹{formatNumber2Dec(depth.ltp)}
              </span>
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: isUp ? '#26a69a' : '#ef5350',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 2,
                }}
              >
                {isUp ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                {change >= 0 ? '+' : ''}
                {change} ({changePct >= 0 ? '+' : ''}
                {changePct}%)
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
                borderRadius: 4,
              }}
            >
              <RefreshCw size={15} className={refreshing ? 'spin' : ''} />
            </button>
            {onClose && (
              <button
                onClick={onClose}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--color-text-muted, #787b86)',
                  cursor: 'pointer',
                  padding: 6,
                }}
              >
                <X size={18} />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Unified 6-Column Kite Market Depth Table (Bid, Orders, Qty, Offer, Orders, Qty) */}
      <div
        style={{
          border: '1px solid var(--color-border, #2a2e39)',
          borderRadius: 6,
          overflow: 'hidden',
          marginBottom: 10,
          background: 'rgba(255, 255, 255, 0.01)',
        }}
      >
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: 12,
            textAlign: 'left',
          }}
        >
          <thead>
            <tr
              style={{
                background: 'var(--color-bg-secondary, #1a1e29)',
                borderBottom: '1px solid var(--color-border, #2a2e39)',
                color: 'var(--color-text-muted, #8c92a4)',
                fontSize: 11,
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: 0.5,
              }}
            >
              <th style={{ padding: '8px 10px', color: '#387ed1' }}>Bid</th>
              <th style={{ padding: '8px 10px', textAlign: 'right' }}>Orders</th>
              <th style={{ padding: '8px 10px', textAlign: 'right', borderRight: '1px solid var(--color-border, #2a2e39)' }}>
                Qty
              </th>
              <th style={{ padding: '8px 10px', color: '#df514c' }}>Offer</th>
              <th style={{ padding: '8px 10px', textAlign: 'right' }}>Orders</th>
              <th style={{ padding: '8px 10px', textAlign: 'right' }}>Qty</th>
            </tr>
          </thead>
          <tbody>
            {[0, 1, 2, 3, 4].map((idx) => {
              const b = bids[idx];
              const a = asks[idx];
              return (
                <tr
                  key={idx}
                  style={{
                    borderBottom: '1px solid rgba(255, 255, 255, 0.03)',
                    transition: 'background 0.15s ease',
                  }}
                >
                  {/* Bid side (Blue) */}
                  <td
                    className="mono depth-cell-click"
                    onClick={() => onTrade && b.price > 0 && onTrade('SELL', b.price)}
                    title={b.price > 0 ? `Click to Sell @ ₹${b.price}` : ''}
                    style={{
                      padding: '7px 10px',
                      color: '#387ed1',
                      fontWeight: 600,
                      cursor: onTrade && b.price > 0 ? 'pointer' : 'default',
                    }}
                  >
                    {formatNumber2Dec(b.price)}
                  </td>
                  <td
                    className="mono"
                    style={{
                      padding: '7px 10px',
                      textAlign: 'right',
                      color: 'var(--color-text-muted, #8c92a4)',
                    }}
                  >
                    {b.orders.toLocaleString('en-IN')}
                  </td>
                  <td
                    className="mono"
                    style={{
                      padding: '7px 10px',
                      textAlign: 'right',
                      fontWeight: 500,
                      borderRight: '1px solid var(--color-border, #2a2e39)',
                      color: '#387ed1',
                    }}
                  >
                    {b.quantity.toLocaleString('en-IN')}
                  </td>

                  {/* Offer / Ask side (Red) */}
                  <td
                    className="mono depth-cell-click"
                    onClick={() => onTrade && a.price > 0 && onTrade('BUY', a.price)}
                    title={a.price > 0 ? `Click to Buy @ ₹${a.price}` : ''}
                    style={{
                      padding: '7px 10px',
                      color: '#df514c',
                      fontWeight: 600,
                      cursor: onTrade && a.price > 0 ? 'pointer' : 'default',
                    }}
                  >
                    {formatNumber2Dec(a.price)}
                  </td>
                  <td
                    className="mono"
                    style={{
                      padding: '7px 10px',
                      textAlign: 'right',
                      color: 'var(--color-text-muted, #8c92a4)',
                    }}
                  >
                    {a.orders.toLocaleString('en-IN')}
                  </td>
                  <td
                    className="mono"
                    style={{
                      padding: '7px 10px',
                      textAlign: 'right',
                      fontWeight: 500,
                      color: '#df514c',
                    }}
                  >
                    {a.quantity.toLocaleString('en-IN')}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr
              style={{
                background: 'rgba(255, 255, 255, 0.02)',
                borderTop: '1px solid var(--color-border, #2a2e39)',
                fontWeight: 700,
                fontSize: 12,
              }}
            >
              <td style={{ padding: '8px 10px', color: '#387ed1' }}>Total</td>
              <td style={{ padding: '8px 10px' }}></td>
              <td
                className="mono"
                style={{
                  padding: '8px 10px',
                  textAlign: 'right',
                  color: '#387ed1',
                  borderRight: '1px solid var(--color-border, #2a2e39)',
                }}
              >
                {totalBidsSum.toLocaleString('en-IN')}
              </td>
              <td style={{ padding: '8px 10px', color: '#df514c' }}>Total</td>
              <td style={{ padding: '8px 10px' }}></td>
              <td
                className="mono"
                style={{
                  padding: '8px 10px',
                  textAlign: 'right',
                  color: '#df514c',
                }}
              >
                {totalAsksSum.toLocaleString('en-IN')}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      {/* Buyer vs Seller Momentum Ratio Split Bar */}
      <div style={{ marginBottom: 12 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: 11,
            fontWeight: 700,
            marginBottom: 4,
          }}
        >
          <span style={{ color: '#387ed1' }}>Buyers: {depth.buy_ratio}%</span>
          <span style={{ color: 'var(--color-text-muted, #787b86)' }}>
            Spread: ₹{depth.spread} ({depth.spread_pct}%)
          </span>
          <span style={{ color: '#df514c' }}>Sellers: {depth.sell_ratio}%</span>
        </div>
        <div
          style={{
            height: 6,
            width: '100%',
            background: '#df514c',
            borderRadius: 3,
            overflow: 'hidden',
            display: 'flex',
          }}
        >
          <div style={{ width: `${depth.buy_ratio}%`, background: '#387ed1', height: '100%' }} />
        </div>
      </div>

      {/* Key Market Statistics Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '6px 12px',
          padding: '10px 12px',
          background: 'rgba(255,255,255,0.02)',
          borderRadius: 6,
          border: '1px solid var(--color-border-light, #1e222d)',
          fontSize: 11,
        }}
      >
        <div>
          <div style={{ color: 'var(--color-text-muted, #787b86)', fontSize: 10 }}>Open</div>
          <div className="mono" style={{ fontWeight: 600 }}>
            ₹{formatNumber2Dec(depth.open)}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--color-text-muted, #787b86)', fontSize: 10 }}>High</div>
          <div className="mono" style={{ fontWeight: 600 }}>
            ₹{formatNumber2Dec(depth.high)}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--color-text-muted, #787b86)', fontSize: 10 }}>Low</div>
          <div className="mono" style={{ fontWeight: 600 }}>
            ₹{formatNumber2Dec(depth.low)}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--color-text-muted, #787b86)', fontSize: 10 }}>Prev. Close</div>
          <div className="mono" style={{ fontWeight: 600 }}>
            ₹{formatNumber2Dec(depth.previous_close)}
          </div>
        </div>

        <div>
          <div style={{ color: 'var(--color-text-muted, #787b86)', fontSize: 10 }}>Volume</div>
          <div className="mono" style={{ fontWeight: 600 }}>
            {depth.volume.toLocaleString('en-IN')}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--color-text-muted, #787b86)', fontSize: 10 }}>
            Avg. Price (ATP)
          </div>
          <div className="mono" style={{ fontWeight: 600 }}>
            ₹{formatNumber2Dec(depth.atp)}
          </div>
        </div>
        <div>
          <div style={{ color: '#df514c', fontSize: 10 }}>Lower Circuit</div>
          <div className="mono" style={{ fontWeight: 600, color: '#df514c' }}>
            ₹{formatNumber2Dec(depth.lower_circuit)}
          </div>
        </div>
        <div>
          <div style={{ color: '#387ed1', fontSize: 10 }}>Upper Circuit</div>
          <div className="mono" style={{ fontWeight: 600, color: '#387ed1' }}>
            ₹{formatNumber2Dec(depth.upper_circuit)}
          </div>
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
              background: '#387ed1',
              color: 'white',
              fontWeight: 700,
              padding: '8px 16px',
              borderRadius: 4,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
            }}
          >
            <ShoppingCart size={14} /> Buy @ ₹{formatNumber2Dec(depth.asks[0]?.price || depth.ltp)}
          </button>
          <button
            className="btn"
            onClick={() => onTrade('SELL', depth.bids[0]?.price || depth.ltp)}
            style={{
              flex: 1,
              background: '#df514c',
              color: 'white',
              fontWeight: 700,
              padding: '8px 16px',
              borderRadius: 4,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
            }}
          >
            <ShoppingCart size={14} /> Sell @ ₹{formatNumber2Dec(depth.bids[0]?.price || depth.ltp)}
          </button>
        </div>
      )}

      <style>{`
        .depth-cell-click:hover {
          background: rgba(255, 255, 255, 0.05);
          text-decoration: underline;
        }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .spin { animation: spin 1s linear infinite; }
      `}</style>
    </div>
  );
}

function round2(num: number): number {
  return Math.round((num + Number.EPSILON) * 100) / 100;
}
