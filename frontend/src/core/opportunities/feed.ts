/** Confidence banding + feed lifecycle.
 *
 * Confidence is EVIDENCE STRENGTH, never probability of profit — the UI
 * repeats this on hover. Bands are computed deterministically here; in
 * Phase 2 the Analyst may shift ±1 band with a stated reason (the shift
 * and reason render on the card).
 *
 * Feed hygiene (design v1.1 §1.3):
 *  - dedup by card id (type|pair|structure): updates refresh, not duplicate
 *  - dismissal => cooldown (no resurrection for COOLDOWN_MS unless the
 *    evidence band ESCALATES — a dismissed WATCH that becomes ACTIONABLE
 *    is new information and may return)
 *  - disappearance without action => `invalidated` (locked decision #3:
 *    ON by default, subtle, structured, outcome-tagged; suppression by
 *    band is a user setting honored at render time, not here — the data
 *    is always recorded, suppression is presentation)
 */
import type { Band, CardStatus, ConfidenceInputs, DismissalReason,
  OpportunityCard } from "./types";

export const COOLDOWN_MS = 12 * 3600_000;

const BAND_RANK: Record<Band, number> = {
  SPECULATIVE: 0, WATCH: 1, ACTIONABLE: 2 };

export function band(c: ConfidenceInputs): Band {
  if (!c.dataQualityOk) return "SPECULATIVE";   // never actionable on flags
  let score = 0;
  if (c.absZ >= 1.5) score++;
  if (c.absZ >= 2.5) score++;
  if (c.persistenceCycles >= 2) score++;
  if (c.modelsAgree) score++;
  if (c.backtestPrior && c.backtestPrior.n >= 20
      && c.backtestPrior.hitRate >= 0.55) score++;
  if (score >= 4) return "ACTIONABLE";
  if (score >= 2) return "WATCH";
  return "SPECULATIVE";
}

export interface FeedState {
  cards: Record<string, OpportunityCard>;
  order: string[];                       // render order, newest/strongest first
}

export const emptyFeed = (): FeedState => ({ cards: {}, order: [] });

function rank(c: OpportunityCard): number {
  return BAND_RANK[c.band] * 1000 + c.confidence.absZ;
}

function resort(s: FeedState): FeedState {
  const live = Object.values(s.cards).filter(
    (c) => !["dismissed", "invalidated", "expired"].includes(c.status));
  const dead = Object.values(s.cards).filter(
    (c) => ["dismissed", "invalidated", "expired"].includes(c.status));
  const order = [
    ...live.sort((a, b) => rank(b) - rank(a)),
    ...dead.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
  ].map((c) => c.id);
  return { ...s, order };
}

/** Apply one cycle's freshly-detected cards to the feed. */
export function applyCycle(s: FeedState, detected: OpportunityCard[],
                           now: string): FeedState {
  const cards = { ...s.cards };
  const seen = new Set<string>();

  for (const d of detected) {
    seen.add(d.id);
    const prev = cards[d.id];
    if (!prev) { cards[d.id] = d; continue; }

    if (prev.status === "dismissed" && prev.dismissal) {
      const cooled = Date.parse(now) - Date.parse(prev.dismissal.at)
        >= COOLDOWN_MS;
      const escalated = BAND_RANK[d.band] > BAND_RANK[prev.band];
      if (!cooled && !escalated) continue;       // stays dismissed
    }
    cards[d.id] = {
      ...d,
      createdAt: prev.createdAt,
      status: ["watching", "acted"].includes(prev.status)
        ? prev.status                            // sticky trader states
        : prev.status === "dismissed" ? "new" : prev.status,
      updatedAt: now,
    };
  }

  // disappearance without action => invalidated (decision #3)
  for (const c of Object.values(cards)) {
    if (seen.has(c.id)) continue;
    if (["new", "seen", "watching"].includes(c.status)) {
      cards[c.id] = {
        ...c, status: "invalidated", updatedAt: now,
        invalidation: { at: now, outcome: "closed without action" },
      };
    }
  }
  return resort({ cards, order: [] });
}

export function transition(s: FeedState, id: string, status: CardStatus,
  now: string,
  dismissal?: { reason: DismissalReason; note?: string }): FeedState {
  const c = s.cards[id];
  if (!c) return s;
  const next: OpportunityCard = { ...c, status, updatedAt: now };
  if (status === "dismissed" && dismissal)
    next.dismissal = { ...dismissal, at: now };
  return resort({ ...s, cards: { ...s.cards, [id]: next } });
}
