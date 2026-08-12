import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Phase 1: ML & AI Model Mathematical Validation', () => {

  const SYMBOL = 'RELIANCE.NS';
  
  // Read token from storageState
  const getAuthHeader = () => {
    const statePath = path.join(__dirname, 'storageState.json');
    if (!fs.existsSync(statePath)) return {};
    const state = JSON.parse(fs.readFileSync(statePath, 'utf-8'));
    const token = state.origins[0]?.localStorage?.find((i: any) => i.name === 'auth_token')?.value;
    return token ? { 'Authorization': `Bearer ${token}` } : {};
  };

  test('Swing Trade Screener constraints (Target > Entry, Stop Loss < Entry for LONG)', async ({ request }) => {
    // We hit the insights endpoint which runs the screener
    const response = await request.get(`http://127.0.0.1:8000/api/stocks/${SYMBOL}/insight`, {
      headers: getAuthHeader()
    });
    expect(response.ok()).toBeTruthy();
    
    const data = await response.json();
    const swingTrade = data.swing_trade;
    
    expect(swingTrade).toBeDefined();
    
    // For a BUY/HOLD signal, target should be above entry, stop loss below entry
    if (swingTrade.action === 'BUY' || swingTrade.action === 'HOLD') {
      expect(swingTrade.trade_plan.target_price).toBeGreaterThan(swingTrade.trade_plan.entry_price);
      expect(swingTrade.trade_plan.stop_loss).toBeLessThan(swingTrade.trade_plan.entry_price);
      expect(swingTrade.trade_plan.expected_gain_pct).toBeGreaterThan(0);
    } else if (swingTrade.action === 'SELL') {
      expect(swingTrade.trade_plan.target_price).toBeLessThan(swingTrade.trade_plan.entry_price);
      expect(swingTrade.trade_plan.stop_loss).toBeGreaterThan(swingTrade.trade_plan.entry_price);
    }
  });

  test('Options Pricing Engine (Black-Scholes theoretical calculation bounds)', async ({ request }) => {
    const response = await request.get(`http://127.0.0.1:8000/api/market/options/${SYMBOL}`, {
      headers: getAuthHeader()
    });
    expect(response.ok()).toBeTruthy();
    
    const data = await response.json();
    expect(data.spot_price).toBeGreaterThan(0);
    expect(data.chain[0].CE.impliedVolatility).toBeGreaterThan(0);
    
    // Check option chain structure
    expect(Array.isArray(data.chain)).toBeTruthy();
    const strikeData = data.chain[0];
    
    // Validate Black-Scholes Greeks
    expect(strikeData.CE.delta).toBeDefined();
    expect(strikeData.CE.gamma).toBeDefined();
    expect(strikeData.CE.theta).toBeLessThanOrEqual(0); // Theta should be negative or 0   
    
    for (let i = 0; i < data.chain.length - 1; i++) {
      if (data.chain[i].strike < data.chain[i+1].strike) {
        // Deep ITM options should be more expensive than OTM options
        expect(data.chain[i].CE.lastPrice).toBeGreaterThanOrEqual(data.chain[i+1].CE.lastPrice);
      }
    }
  });
  
  test('AI ML Scoring Engine generates valid values', async ({ request }) => {
    const response = await request.get(`http://127.0.0.1:8000/api/stocks/${SYMBOL}/ai-score`, {
      headers: getAuthHeader()
    });
    expect(response.ok()).toBeTruthy();
    
    const score = await response.json();
    expect(["BUY", "HOLD", "SELL"]).toContain(score.score);
    
    // Validate SHAP explanations exist
    expect(score.explanation).toBeDefined();
    expect(score.explanation.length).toBeGreaterThan(0);
  });

});
