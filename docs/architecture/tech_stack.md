# Technology Stack

## Backend
| Component | Technology | Version | Reason |
|-----------|-----------|---------|--------|
| API Framework | FastAPI | 0.111+ | Async, auto-docs, high performance |
| Language | Python | 3.11 | Best ML/quant ecosystem |
| ORM | SQLAlchemy | 2.0 | Async ORM, type-safe |
| Migrations | Alembic | 1.13+ | Version-controlled schema |
| Task Queue | Celery | 5.3+ | Background ingestion, alert eval |
| Data fetching | yfinance | 0.2+ | Free NSE/BSE OHLCV data |
| Indicators | pandas-ta | 0.3+ | 130+ technical indicators |
| AI/ML | LightGBM, scikit-learn | latest | Fast gradient boosting |
| Explainability | SHAP | 0.44+ | Feature importance for all models |
| Auth | python-jose, passlib | latest | JWT tokens, password hashing |
| Validation | Pydantic v2 | 2.x | Request/response validation |
| Testing | pytest, pytest-asyncio | latest | Unit + async tests |

## Frontend
| Component | Technology | Version | Reason |
|-----------|-----------|---------|--------|
| UI Framework | React | 18.x | Component model, ecosystem |
| Build Tool | Vite | 5.x | Fastest HMR, optimised builds |
| Language | TypeScript | 5.x | Type safety |
| Routing | React Router | 6.x | Declarative routing |
| State | Zustand | 4.x | Simple, no boilerplate |
| Charting | Lightweight Charts | 4.x | TradingView OSS candlestick engine |
| HTTP Client | Axios | 1.x | Interceptors, error handling |
| Styling | Vanilla CSS + CSS Modules | — | No external CSS framework |
| WebSocket | native WebSocket API | — | Real-time alert delivery |
| Icons | Lucide React | latest | Consistent icon set |
| Testing | Vitest, React Testing Library | latest | Fast unit tests |

## Database & Infrastructure
| Component | Technology | Version | Reason |
|-----------|-----------|---------|--------|
| Database | PostgreSQL | 15 | Reliable, extensible |
| Time-series | TimescaleDB | 2.x | OHLCV hypertables, compression |
| Cache | Redis | 7 | Quote cache, Celery broker |
| Container | Docker | latest | Dev environment consistency |
| Orchestration | Docker Compose | 2.x | Local multi-service orchestration |
| Monitoring | Flower | 2.x | Celery task monitoring |
| Reverse Proxy | Nginx | 1.25+ | Static files + API proxy (prod) |

## Data Sources
| Source | Use | Cost | Limitations |
|--------|-----|------|-------------|
| yfinance | OHLCV, company info | Free | 15-min delay, no tick data |
| NSE website | Index compositions, circuit filters | Free | Scraping, may break |
| BSE website | Corporate actions | Free | Scraping, may break |
| Upstox API | Live market feed | Requires account | Phase 5+ |
| Fyers API | Live market feed | Requires account | Phase 5+ |

## AI/ML Stack
| Stage | Technology | When |
|-------|-----------|------|
| Indicators | pandas-ta | Phase 4 |
| Rule-based signals | Pure Python | Phase 5 |
| ML scoring | LightGBM + scikit-learn | Phase 9 |
| Explainability | SHAP | Phase 9 |
| Regime detection | HMM / LSTM | Phase 10 |
| Deep learning | PyTorch (optional) | Phase 11+ |
