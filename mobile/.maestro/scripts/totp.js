/* global http, output */
// Fetches a fresh 2FA code at the moment the flow needs it, from the CI-only helper on the runner
// (.github/scripts/totp_server.py, bound to 127.0.0.1). Maestro runs this script on the host, not in the app.
const response = http.get('http://127.0.0.1:5055/totp');
if (response.status !== 200) {
  throw new Error('TOTP helper answered ' + response.status);
}
output.MFA_CODE = response.body.trim();
