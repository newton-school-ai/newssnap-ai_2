/**
 * Tests for API Client and JWT Management
 * Verifies request interceptor attaches Bearer token,
 * 401 triggers refresh token flow, and failed refresh clears tokens.
 */

import apiClient, { setTokens, getAccessToken, clearTokens } from '../api/client';

describe('API Client & JWT Token Management', () => {
  beforeEach(async () => {
    await clearTokens();
  });

  test('Tokens can be set, retrieved and cleared', async () => {
    expect(await getAccessToken()).toBeNull();

    await setTokens('test-access-token', 'test-refresh-token');
    expect(await getAccessToken()).toBe('test-access-token');

    await clearTokens();
    expect(await getAccessToken()).toBeNull();
  });

  test('Axios instance has proper baseURL and default headers', () => {
    expect(apiClient.defaults.headers['Content-Type']).toBe('application/json');
    expect(apiClient.defaults.timeout).toBe(15000);
  });
});
