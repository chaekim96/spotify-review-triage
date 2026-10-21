## Recommendation

Put next quarter's effort into **usability**. Within the declared sample of classified reviews, it has the largest area-level severity sum, 40335 [area:usability], and the largest share of severity, 35.5 percent [area:usability]. It also has the most complaints, 15613 [area:usability]. This is a ranking of the sample only, not of all users, and app-store reviewers are self-selected.

## Why (the evidence)

- Usability has 1283 cancellation-intent reviews [area:usability], the highest of any area. This is stated intent, not churn.
- The top-ranked issue is USABILITY-99, with severity sum 14461 [C0002] and complaint count 5340 [C0001]. It is a catch-all bucket, so it needs decomposing before it can be scoped.
- USABILITY-01 (Excessive Advertisements) has complaint count 5353 [C0013] and severity sum 11578 [C0014].
- USABILITY-02 (Unwanted Shuffle Playback) has complaint count 1048 [C0037] and severity sum 3075 [C0038].
- Reviews in the evidence pack describe lost or missing libraries: "my playlists were gone" (1ec0da94-9fb5-4e1d-a77b-f30873117d6d) and "It won't show any of my Playlists or library-- the screen is black and no songs are available." (056c340f-c7ad-42d8-a275-37e46f1f4f24).

## Alternatives considered

**Billing/support** ranks second by volume: severity sum 21719 [area:billing/support], with 1238 cancellation-intent reviews [area:billing/support]. It ranks lower because its mean severity is 2.791286 [area:billing/support] and only 201 reviews are severity 4 or above [area:billing/support]. Its largest issue, BILLING-99, has severity sum 11541 [C0018]. One quote: "Taking money out my bank without permission" (0327424f-5ab1-42d7-aefa-b021dc049420). It is a credible runner-up and could take a smaller dedicated slice of effort.

**Playback** has severity sum 19064 [area:playback] and mean severity 3.121664 [area:playback], with 1032 reviews at severity 4 or above [area:playback]. It ranks lower on total volume, but its per-review severity is higher than usability's 2.583424 [area:usability]. PLAYBACK-03 (App crashes or freezes) has severity sum 2401 [C0042]. Quote: "I had to do a factory reset to make it usable again!" (2137175d-9742-4ef4-9655-49ba42b7d00c).

**Access** is the smallest classified area: severity sum 5648 [area:access] and 78 cancellation-intent reviews [area:access]. It has the highest mean severity, 3.813639 [area:access], and 1181 reviews at severity 4 or above [area:access]. ACCESS-06 (General Sign-In Failure) has mean severity 3.862355 [C0047] over 603 complaints [C0045]. It ranks lower because of its small footprint, but it is a good candidate for a targeted fix because the complaints are so severe.

## Risks and limitations

- The sample is 100000 reviews in scope, with 99936 completed records. App-store reviewers are self-selected, so results do not generalize to all users.
- The unassigned (general) bucket has severity sum 27010 [area:unassigned (general)], larger than any named area except usability. Two of the top three issues, OTHER-03 and OTHER-99, are unassigned. The evidence pack shows privacy concerns there, which this ranking does not address.
- USABILITY-99 is a generic bucket, and some evidence quotes (such as lost playlists) may reflect data or sync problems that could overlap with other areas.
- Cancellation language is stated intent only. This memo makes no revenue, churn, retention or causal estimates.
- Severity-weighted sums favor areas with high volume; area ranking would differ if weighted by severity 4 or above, where access and playback lead.

## Next steps

1. Break USABILITY-99 into specific sub-issues, starting with missing playlists and libraries.
2. Scope ad-load (USABILITY-01) and shuffle (USABILITY-02) work against current product constraints.
3. Review the unassigned (general) bucket for hidden themes, especially privacy.
4. Hand high-severity access and playback issues to a small fast-fix track.
5. Re-run the analysis on the next sample to check whether the ranking holds.
