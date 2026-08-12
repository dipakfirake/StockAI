import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { X, TrendingUp, TrendingDown, Star, Trash2, Plus } from 'lucide-react';
import { watchlistApi } from '../services/api';
import StockSearchBox from './StockSearchBox';
import './WatchlistSidebar.css';

interface WatchlistSidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function WatchlistSidebar({ isOpen, onClose }: WatchlistSidebarProps) {
  const navigate = useNavigate();
  const [stocks, setStocks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [newSymbol, setNewSymbol] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  const fetchWatchlist = async () => {
    try {
      const res = await watchlistApi.get();
      setStocks(res.data.stocks || []);
    } catch (err) {
      console.error("Watchlist fetch error", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    fetchWatchlist();
    const interval = setInterval(fetchWatchlist, 30000); // 30s refresh
    return () => clearInterval(interval);
  }, [isOpen]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSymbol.trim()) return;
    try {
      setIsAdding(true);
      await watchlistApi.add(newSymbol.toUpperCase());
      setNewSymbol('');
      fetchWatchlist();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to add stock');
    } finally {
      setIsAdding(false);
    }
  };

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
                      navigate(`/chart/${q.symbol}`);
                      onClose();
                    }}
                  >
                    <div className="wl-left">
                      <span className="wl-symbol">{q.symbol.replace('.NS', '')}</span>
                      <span className="wl-price">₹{q.price?.toFixed(2) || '0.00'}</span>
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
