/** The pending second-step challenge, in memory only (never in a route parameter or on disk). */
import type { MfaChallenge } from '../api/schemas';

let challenge: { value: MfaChallenge; email: string } | null = null;

export function setMfaChallenge(value: MfaChallenge, email: string): void {
  challenge = { value, email };
}

export function getMfaChallenge(): { value: MfaChallenge; email: string } | null {
  if (challenge && Date.parse(challenge.value.mfa_expires_at) <= Date.now()) challenge = null;
  return challenge;
}

export function clearMfaChallenge(): void {
  challenge = null;
}
