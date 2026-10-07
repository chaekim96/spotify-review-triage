# Label definitions (labels-v1)

Classify the review text only. Star rating, app version and date are not shown and must not be guessed.

## topic (exactly one)

| topic | Use for |
|---|---|
| access | Login, signup, password or account access |
| usability | Navigation, controls, layout, queue/playlist management, ad interruptions |
| playback | Playback failure, crashes, lag, connection failures, audio quality, resource use |
| downloads | Downloading, saved music, offline listening, disappearing downloads |
| catalog | Missing songs/artists, search/discovery, recommendations, lyrics availability |
| billing | Price, charges, subscriptions, paywalls, premium entitlement; controls the review explicitly says are premium-only |
| support | Contacting support and the support response |
| other | General praise or criticism, unrelated content, or no supported specific topic |

Rules:
- Several problems: pick the one with the highest severity. On a tie, pick the first specific problem mentioned.
- Positive review: pick the first specific praised feature. General praise ("great app") is `other`.
- A paid plan being mentioned does not make the topic `billing`. A subscription failing to activate is `billing`; music crashing for a paying customer is `playback`.
- A control (shuffle, seeking, repeat, picking a song, lyrics) is `billing` only when the review says it is locked behind payment or premium. Otherwise it is `usability` (or `catalog` for lyrics availability).
- "Something went wrong", "not working", "bad app" with no named feature: `other`. Do not invent a specific defect.

## intent (exactly one, first match wins)

1. `cancellation`: explicitly leaving, uninstalling, cancelling, or threatening to ("going to uninstall", "switching to X", "cancelled my subscription").
2. `complaint`: a negative experience, including mixed praise and criticism.
3. `request`: asks for a change or feature without reporting a failure.
4. `praise`: positive only.
5. `unclear`: meaningless, unrelated, or a bare boycott slogan with no product complaint and no explicit personal departure.

## severity (integer 1 to 5)

| severity | Meaning |
|---|---|
| 1 | No reported problem: praise, neutral or unclear content, or a pure feature request |
| 2 | Dislike, generic criticism, minor annoyance (including ads), or a cosmetic issue; no supported loss of function |
| 3 | A degraded or restricted function; some use or a workaround remains |
| 4 | A clearly blocked core task, such as being unable to log in or play music at all |
| 5 | Explicit serious financial, privacy or data harm (for example repeated unauthorized charges, a confirmed account takeover, lost personal data) |

Severity follows the reported impact, not the tone. Stars, angry language, an expensive plan, a crash on its own, or cancellation intent never raise severity by themselves. Suspected or hedged harm ("looks like I was hacked") stays below 5 and sets `needs_review`.

## sentiment (number from -1 to 1)

Overall feeling of the text: -1 very negative, -0.5 negative, 0 neutral or evenly mixed, 0.5 positive, 1 very positive. Use one decimal place.

## entities (list of strings)

Named products, plans, features, devices, apps, companies or places in the text, written as they appear ("spotify premium", "Jam", "YouTube", "android"). Do not include "Spotify" or "app" on their own. Use `[]` when there are none. Never include personal names.

## evidence_quote (string)

A short, exact, character-for-character copy of the part of the review that supports the topic and intent. Copy it from the review text without fixing spelling, case, spacing or emoji. For a very short review, quote the whole review.

## needs_review (true or false)

`true` when the text lacks the context to label confidently: unclear what failed, hedged claims, mixed languages you cannot read well, or two labels that fit equally. Otherwise `false`.
