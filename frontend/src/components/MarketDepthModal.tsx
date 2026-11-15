import React from 'react';
import MarketDepthWidget from './MarketDepthWidget';

interface MarketDepthModalProps {
  isOpen: boolean;
  symbol: string;
  onClose: () => void;
  onTrade?: (direction: 'BUY' | 'SELL', price?: number) => void;
}

export default function MarketDepthModal({ isOpen, symbol, onClose, onTrade }: MarketDepthModalProps) {
  if (!isOpen || !symbol) return null;

  return (
    <div 
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(3px)',
        zIndex: 99999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <MarketDepthWidget symbol={symbol} onClose={onClose} onTrade={onTrade} />
    </div>
  );
}
