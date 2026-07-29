import httpx, time
token=httpx.post('http://localhost:8000/api/auth/login', data={'username':'admin@stockai.com', 'password':'admin'}).json()['access_token']
res=httpx.post('http://localhost:8000/api/backtest/run', json={'symbol': 'RELIANCE.NS', 'strategy': 'rsi_mean_reversion', 'start_date': '2022-01-01', 'end_date': '2023-01-01', 'initial_capital': 100000}, headers={'Authorization': 'Bearer '+token}).json()
print(res)
time.sleep(4)
print(httpx.get(f"http://localhost:8000/api/backtest/{res['backtest_id']}/results", headers={'Authorization': 'Bearer '+token}).json())
