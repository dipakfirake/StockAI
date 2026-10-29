import { request } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

async function globalSetup() {
  const requestContext = await request.newContext({
    baseURL: 'http://127.0.0.1:8000',
    timeout: 10000,
  });
  const TEST_EMAIL = `test_QA_GLOBAL_${Date.now()}@stockai.com`;
  const TEST_PASSWORD = 'SecurePassword123!';

  // 0. Verify the backend is reachable before attempting registration
  try {
    const healthResponse = await requestContext.get('/health');
    if (!healthResponse.ok()) {
      throw new Error(`Backend health check returned ${healthResponse.status}`);
    }
  } catch (error) {
    console.error('Initial health check failed, retrying on localhost...', error);
    try {
      const retryContext = await request.newContext({ baseURL: 'http://localhost:8000', timeout: 15000 });
      const retryResp = await retryContext.get('/health');
      if (!retryResp.ok()) {
        throw new Error(`Backend health check returned ${retryResp.status}`);
      }
    } catch (retryErr) {
      throw new Error(
        `Playwright global setup failed: backend is not reachable. Error: ${error} | Retry error: ${retryErr}`
      );
    }
  }

  // 1. Register the test user
  await requestContext.post('/api/auth/register', {
    data: {
      email: TEST_EMAIL,
      name: 'Global QA Robot',
      password: TEST_PASSWORD
    }
  });

  // 2. Login the test user to get the JWT token
  const loginResponse = await requestContext.post('http://127.0.0.1:8000/api/auth/login', {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    form: {
      username: TEST_EMAIL,
      password: TEST_PASSWORD
    }
  });

  const authData = await loginResponse.json();
  const token = authData.access_token;

  if (!token) {
    throw new Error('Global Setup Failed: Could not get JWT token from login endpoint.');
  }

  // 3. Upgrade the test user to PRO so the full platform UI is available during E2E validation
  await requestContext.post('http://127.0.0.1:8000/api/auth/upgrade', {
    headers: {
      Authorization: `Bearer ${token}`
    }
  });

  // 4. Save the token and cookie consent into the storageState format expected by Playwright for localStorage
  const consentObj = {
    essential: true,
    security: true,
    location: false,
    timestamp: new Date().toISOString(),
    version: '2023.1'
  };

  const storageState = {
    cookies: [
      {
        name: 'dpdpa_consent_v1',
        value: encodeURIComponent(JSON.stringify(consentObj)),
        domain: 'localhost',
        path: '/',
        expires: Math.floor(Date.now() / 1000) + 31536000,
        httpOnly: false,
        secure: false,
        sameSite: 'Lax' as const
      }
    ],
    origins: [
      {
        origin: 'http://localhost:5173',
        localStorage: [
          {
            name: 'auth_token',
            value: token
          },
          {
            name: 'stockai_dpdpa_consent',
            value: JSON.stringify(consentObj)
          }
        ]
      }
    ]
  };

  const statePath = path.join(__dirname, 'storageState.json');
  fs.writeFileSync(statePath, JSON.stringify(storageState));
  console.log('✅ Global Authentication Setup Complete.');
}

export default globalSetup;
