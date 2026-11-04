import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { X, TrendingUp, TrendingDown, Star, Trash2 } from 'lucide-react';
import { watchlistApi } from '../services/api';
import StockSearchBox from './StockSearchBox';
import { formatINR } from '../utils/formatters';
import { isWebSocketSupportedOnHost } from '../services/websocket';
import './WatchlistSidebar.css';

interface WatchlistSidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

const cleanSym = (s: string | null | undefined): string => {
  if (!s) return '';
  return String(s).replace(/^NSE:|^BSE:/, '').replace(/\.NS$|\.BO$/, '').replace(/^\^/, '').toUpperCase();
};

export default function WatchlistSidebar({ isOpen, onClose }: WatchlistSidebarProps) {
  const navigate = useNavigate();
  const [stocks, setStocks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [, setIsAdding] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const fallbackPollTimerRef = useRef<number | null>(null);
  const pendingTicksRef = useRef<Map<string, any>>(new Map());
  const rafIdRef = useRef<number | null>(null);
  const isWsConnectedRef = useRef<boolean>(false);
  const stocksRef = useRef<any[]>([]);

  stocksRef.current = stocks;

  const fetchWatchlist = async () => {
    try {
      const res = await watchlistApi.get();
      const list = res.data.stocks || [];
      setStocks(list);
      // Subscribe all loaded symbols over WebSocket if connected
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        list.forEach((item: any) => {
          if (item.symbol) {
            wsRef.current?.send(JSON.stringify({
              type: 'subscribe',
              channel: 'market_data',
              symbol: item.symbol,
            }));
          }
        });
      }
    } catch (err) {
      console.error("Watchlist fetch error", err);
    } finally {
      setLoading(false);
    }
  };

  const startFallbackPoll = useCallback(() => {
    if (fallbackPollTimerRef.current === null) {
      fallbackPollTimerRef.current = window.setInterval(fetchWatchlist, 30000); // 30s slow poll only if WS down
    }
  }, []);

  const stopFallbackPoll = useCallback(() => {
    if (fallbackPollTimerRef.current !== null) {
      window.clearInterval(fallbackPollTimerRef.current);
      fallbackPollTimerRef.current = null;
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    const token = localStorage.getItem('auth_token');
    if (!token || !isWebSocketSupportedOnHost()) return;
    if (reconnectTimerRef.current !== null) return;

    reconnectAttemptsRef.current += 1;
    // Exponential backoff: 1s, 1.5s, 2.25s, max 15s with 0-500ms jitter
    const delay = Math.min(15000, 1000 * Math.pow(1.5, reconnectAttemptsRef.current - 1)) + Math.random() * 500;

    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null;
      connectWs();
    }, delay);
  }, []);

  const connectWs = useCallback(() => {
    const token = localStorage.getItem('auth_token');
    if (!token || !isWebSocketSupportedOnHost()) {
      startFallbackPoll();
      return;
    }

    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.onclose = null;
      try { wsRef.current.close(); } catch (_) {}
      wsRef.current = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    try {
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/?token=${token}`);
      wsRef.current = ws;

      ws.onopen = () => {
        isWsConnectedRef.current = true;
        reconnectAttemptsRef.current = 0;
        stopFallbackPoll();
        // Subscribe all current symbols
        stocksRef.current.forEach((item: any) => {
          if (item.symbol && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: 'subscribe',
              channel: 'market_data',
              symbol: item.symbol,
            }));
          }
        });
      };

      ws.onerror = () => {
        isWsConnectedRef.current = false;
      };

      ws.onclose = (event: CloseEvent) => {
        isWsConnectedRef.current = false;
        startFallbackPoll();
        if (event.code === 1008 || event.code === 4401 || event.code === 4003) {
          if (reconnectTimerRef.current !== null) {
            window.clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
          }
          return;
        }
        scheduleReconnect();
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'market_update' && data.symbol) {
            const sym = cleanSym(data.symbol);
            const newPrice = Number(data.price);
            if (Number.isFinite(newPrice) && newPrice > 0) {
              pendingTicksRef.current.set(sym, {
                price: newPrice,
                change: data.change,
                change_pct: data.change_pct !== undefined ? data.change_pct : data.change_percent,
                volume: data.volume,
              });

              // RAF batching: flush at most once per display frame
              if (rafIdRef.current === null) {
                rafIdRef.current = requestAnimationFrame(() => {
                  rafIdRef.current = null;
                  if (pendingTicksRef.current.size === 0) return;

                  const batch = new Map(pendingTicksRef.current);
                  pendingTicksRef.current.clear();

                  setStocks((prev) => {
                    let hasChanged = false;
                    const next = prev.map((item) => {
                      const itemSym = cleanSym(item.symbol);
                      const tick = batch.get(itemSym);
                      if (!tick || Number(item.price) === tick.price) {
                        return item;
                      }
                      hasChanged = true;
                      return {
                        ...item,
                        price: tick.price,
                        change: tick.change !== undefined ? tick.change : item.change,
                        change_pct: tick.change_pct !== undefined ? tick.change_pct : item.change_pct,
                        volume: tick.volume !== undefined ? tick.volume : item.volume,
                      };
                    });
                    return hasChanged ? next : prev;
                  });
                });
              }
            }
          }
        } catch (_) {}
      };
    } catch (e) {
      startFallbackPoll();
      scheduleReconnect();
    }
  }, [scheduleReconnect, startFallbackPoll, stopFallbackPoll]);

  useEffect(() => {
    if (!isOpen) return;

    setLoading(true);
    fetchWatchlist();
    connectWs();

    return () => {
      stopFallbackPoll();
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onerror = null;
        wsRef.current.onclose = null;
        try {
          if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
            wsRef.current.close();
          }
        } catch (_) {}
        wsRef.current = null;
      }
      isWsConnectedRef.current = false;
    };
  }, [isOpen, connectWs, stopFallbackPoll]);

  const handleRemove = async (e: React.MouseEvent, symbol: string) => {
    e.stopPropagation();
    try {
      await watchlistApi.remove(symbol);
      setStocks(stocks.filter(s => s.symbol !== symbol));
    } catch (err) {
      console.error("Failed to remove", err);
    }
  };

  if (!isOpen) return null;

  return (
    <>
      <div className="watchlist-overlay" onClick={onClose} />
      <div className="watchlist-sidebar">
        <div className="watchlist-header">
          <h2><Star size={18} className="star-icon" /> My Watchlist</h2>
          <button className="icon-btn" onClick={onClose}><X size={20} /></button>
        </div>
        
        <div className="watchlist-add-form" style={{ padding: '12px', borderBottom: '1px solid var(--border)', background: 'var(--bg-card)' }}>
          <StockSearchBox 
            placeholder="Search company to add..." 
            width="100%" 
            autoNavigate={false} 
            clearOnSelect={true}
            onSelect={async (symbol) => {
              try {
                setIsAdding(true);
                await watchlistApi.add(symbol);
                fetchWatchlist();
              } catch (err: any) {
                alert(err.response?.data?.detail || 'Failed to add stock');
              } finally {
                setIsAdding(false);
              }
            }}
          />
        </div>

        <div className="watchlist-content">
          {loading && stocks.length === 0 ? (
            <div className="watchlist-loading">
              <div className="skeleton-line" />
              <div className="skeleton-line" />
              <div className="skeleton-line" />
            </div>
          ) : stocks.length === 0 ? (
            <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-secondary)' }}>
              Your watchlist is empty.
            </div>
          ) : (
            <ul className="watchlist-list">
              {stocks.map(q => {
                const isUp = (q.change || 0) >= 0;
                return (
                  <li 
                    key={q.symbol} 
                    className="watchlist-item"
                    onClick={() => {
                      navigate('/chart', { state: { symbol: q.symbol } });
                      onClose();
                    }}
                  >
                    <div className="wl-left">
                      <span className="wl-symbol">{q.symbol.replace('.NS', '')}</span>
                      <span className="wl-price">{formatINR(q.price)}</span>
                    </div>
                    <div className={`wl-right ${isUp ? 'text-green' : 'text-red'}`}>
                      {isUp ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                      <span>{q.change > 0 ? '+' : ''}{q.change_pct?.toFixed(2) || '0.00'}%</span>
                      <button 
                        className="wl-remove-btn" 
                        onClick={(e) => handleRemove(e, q.symbol)}
                        title="Remove from Watchlist"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>
    </>
  );
}
