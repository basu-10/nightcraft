# NEERA Implementation Checklist

NEERA is a Goodreads-like arts platform with customizable user profiles, item-centric review pages, list pages, notes/posts, and a social feed. This checklist turns the product plan into buildable issues with explicit progress tracking.

## Execution Order

1. Scaffold the NEERA app and align it with the existing radio-app structure.
2. Implement auth, profile storage, and user profile layout foundations.
3. Add category taxonomy and seeded item catalog for day-1 reviews.
4. Build item pages, review flows, and user-submitted item contribution flows.
5. Build lists, notes, posts, reactions, and post-only comments with owner controls.
6. Add following plus global/following feed behavior.
7. Finish privacy, moderation, search, and confidence-scoring UX.
8. Prepare deployment wiring, documentation, and regression testing.

## Current Implementation Status

Legend:
- `COMPLETE` = implemented and verified
- `IN PROGRESS` = partially implemented or actively being built
- `NOT STARTED` = planned only

| Issue | Progress | Completed | In Progress | Notes |
| --- | --- | --- | --- | --- |
| 1 - Scaffold NEERA app structure | IN PROGRESS | App package, app factory, config, CLI setup command, startup scripts, templates/static scaffold | Production-facing routes and deployment wiring | Aligned with radio-style layout and platform-infra startup integration |
| 2 - Add auth adapter layer | COMPLETE | Local auth blueprint, SSO auth blueprint, current-user helper abstraction, mode-based auth blueprint selection, focused SSO tests | Broader integration coverage against expanded app routes | Product routes are mode-agnostic via shared auth helper interfaces |
| 3 - Add core profile models | COMPLETE | Profile table and persistence fields for display name, bio, avatar/background URLs, link/location, accent settings, visibility, and timestamps | Richer profile management UX | Profile persistence is now DB-backed for both local and SSO-linked users |
| 4 - Build public account page | IN PROGRESS | Public profile route now renders persisted profile data plus DB-backed reviews/lists | Category filtering/grouping and richer timeline behavior | Profile page now reads from product DB records instead of static sample payload |
| 5 - Build lists page | IN PROGRESS | Dedicated lists routes/pages (`/u/<username>/lists`, `/me/lists`) now render persisted lists with owner management controls | Category-specific presentation refinements and list discovery UX | Lists are no longer only embedded in the profile page |
| 6 - Add review model and posting flow | IN PROGRESS | Added `review` model, profile-page rendering, create/edit/delete flows, search-first review composition, and focused tests | Richer review metadata and expanded non-book composition UX | Reviews can now be created from profile and item-linked composition flows |
| 7 - Add list and list-item models | IN PROGRESS | Added `neera_list` and `neera_list_item` models with ordered items, add/delete flows, reorder controls, and focused tests | Fuller item metadata and dedicated list management screens | Lists now persist ordered entries and support mutation from the profile page |
| 8 - Add category styling system | NOT STARTED | None yet | Assign colored containers and reusable style rules per list type | Different list types should feel visually distinct |
| 9 - Add profile customization uploads | IN PROGRESS | URL-based profile header edit flow for background image, avatar image, location, and profile link | File upload pipeline, storage policy, and media validation hardening | Header presentation is now owner-driven even before upload storage is introduced |
| 10 - Add follow relationships | NOT STARTED | None yet | Create follow/unfollow storage and social graph queries | Feed content depends on who a user follows |
| 11 - Build social feed timeline | IN PROGRESS | Added feed tab routes/pages, review `feed_event` pointer emission on publish, and read-time event resolution on profile feed views | Follow graph, global-vs-following modes, and note/post/list event fan-out | Feed is now populated for published non-private reviews but social graph behavior is still pending |
| 12 - Add search and discovery | NOT STARTED | None yet | Search users, lists, reviews, and categories | Useful once core content and feed are stable |
| 13 - Add privacy and moderation controls | NOT STARTED | None yet | Define public/private profile options and content visibility rules | Needed before wider sharing and growth features |
| 14 - Add tests for core flows | IN PROGRESS | Added focused NEERA tests for owner-only composer visibility, list/review create-edit-delete flows, ordered list-item insertion/reordering, and SSO callback/session mutation paths | Broader auth/profile/feed coverage and end-to-end shared-mode integration tests | The current profile and auth mutation slice is covered by targeted pytest checks |
| 15 - Prepare deployment and docs | IN PROGRESS | NEERA README, env example, dev-start script, dev-windows run/seed/setup wiring, NEERA-focused setup/run scripts, and deprecated windows-dev forwarding wrappers | Linux/system-service deployment notes and final validation checklist | Shared-mode startup and seeding include NEERA alongside radio/service-auth |
| 16 - Add category taxonomy and seeded catalog | IN PROGRESS | Added `neera_item` model, taxonomy-backed seeded catalog data, idempotent `seed-catalog` command, setup-time catalog seeding, and `/items` browse route | Expand metadata contracts and deeper category-specific validation | Fresh setups now load seeded entries across book/song/arts/films |
| 17 - Build item details page (2-column) | IN PROGRESS | Added `/items/<item_id>` two-column template with item header/actions, ratings block, metadata panel, and review stream placeholder | Related lists previews, discussions, and richer rating breakdown UX | Item pages now exist as navigable foundations for the full Issue 17 contract |
| 18 - Add user-submitted item contribution flow | IN PROGRESS | Added create-missing-book path in review flow, persisted user-submitted items, and item-level confidence defaults | Extend contribution flow to non-book categories and per-field confidence badges | Users can create a missing book and publish a linked first review in one journey |
| 19 - Add notes and posts content types | NOT STARTED | None yet | Persist markdown notes and posts; add mention graph integration and profile tab rendering | Needed for post-centric interaction and discussion depth |
| 20 - Add reactions and post-only comments | NOT STARTED | None yet | Reactions on reviews/lists/notes/posts; comments only on posts with owner moderation toggles | Core social interaction loop with simpler moderation |
| 21 - Redesign profile page and highlights | IN PROGRESS | Hero layout, overlays, profile strip, highlights block, tabbed interface, and owner-only Bookmarks tab visibility contract | Pin/highlight persistence and full tab content implementations | New profile shell now follows the product blueprint direction |
| 22 - Expand feed behavior and visibility propagation | IN PROGRESS | Review publish flow now emits pointer-style `feed_event` rows and profile feed resolves review visibility from target reads | Add global/following modes plus non-review event types and stricter fan-out controls | Critical for anti-spam and privacy correctness |

## What Is Left Right Now

Focus for product work (excluding server setup/deployment for now):

- Finish Issue 6 and Issue 18 by expanding the search-first create-and-review journey to songs/films/arts.
- Finish Issue 17 by completing related-lists, tags, discussions, and richer ratings blocks on item pages.
- Begin Issue 19 with a minimal post model plus note CRUD to unlock content beyond reviews.
- Begin Issue 20 with heart reactions and post-only flat comments with owner moderation toggles.
- Start Issue 10 and Issue 22 together so follow graph queries and feed visibility semantics evolve as one contract.
- Complete Issue 8 and Issue 12 once the above core social/content surfaces are stable.
- Expand Issue 14 with end-to-end tests around private/draft visibility, feed-event pointer behavior, and contribution flow regressions.

## Milestone Breakdown

### Milestone 1 - App Foundation

- [x] Create NEERA application folder and package layout.
- [x] Add Flask app factory, config classes, and extension bootstrap.
- [x] Add basic templates, static assets, and layout shell.
- [x] Add setup command and local dev startup path.
- [x] Confirm the app can run standalone.

### Milestone 2 - Identity and Profiles

- [x] Add local and SSO auth adapters.
- [x] Add current-user helper abstraction.
- [x] Create account/profile persistence models.
- [ ] Add profile settings for bio, display name, avatar, and background image.
- [x] Add public profile route for account page and lists page.

### Milestone 3 - Reviews and Lists

- [x] Add review model and review creation flow.
- [x] Add list model with arbitrary list categories.
- [x] Add list item model and ordering support.
- [ ] Render category-specific list containers.
- [ ] Enforce typed-list constraints (`book`, `film`, `song`, `art`) and mixed-list composition (`works` + `notes` + `posts`).
- [x] Show all reviews on the account page.

### Milestone 4 - Social Feed

- [ ] Add follow/unfollow relationships.
- [ ] Build feed query logic from followed accounts.
- [ ] Add timeline page for reviews and profile activity.
- [ ] Add post/review composition flow for the logged-in user.
- [ ] Define feed ordering and empty-state behavior.
- [ ] Emit feed events only on public/followers-visible publish.
- [ ] Skip feed events for drafts, private content, and quiet-save updates.
- [ ] Enforce target visibility checks at feed read time.

### Milestone 5 - Customization, Search, and Polish

- [ ] Add background image upload and storage handling.
- [ ] Add theme or accent color preferences.
- [ ] Add search for people, lists, and reviews.
- [ ] Add visibility rules for public and private content.
- [ ] Add accessibility and responsive layout checks.
- [ ] Add post-only comment lifecycle and moderation controls.

### Milestone 6 - Validation and Deployment

- [ ] Add unit and integration tests for each core feature.
- [ ] Add fixture data for sample users, reviews, and lists.
- [x] Document local setup and environment variables.
- [x] Add deployment notes for standalone and shared-auth usage.
- [ ] Verify the app can be deployed alongside the existing ecosystem.

### Milestone 7 - Item-Centric Experience and Trust Signals

- [ ] Add taxonomy and seeded items for book/song/arts/films.
- [ ] Build item pages with the required two-column layout and sections.
- [ ] Implement user-submitted item contribution with confidence score.
- [ ] Add per-field confidence badges (red/yellow/green) for user-submitted metadata only.
- [ ] Add item reference discussions (notes/posts via @ mention).

## Detailed Issue Checklist


## Issue 8 - Add category styling system

Objective:
Make list types visually distinct while keeping the UI coherent.

Status tracker:
- [ ] Complete
- [ ] In progress
- [x] Not started

Checklist:
- Define category-to-style mapping.
- Add reusable colored container styles.
- Support default styles for unknown custom categories.
- Ensure colors remain accessible and readable.

Acceptance criteria:
- Different list types render with distinct, consistent styling.
- Custom categories still get a safe default presentation.

Depends on:
- Issue 5
- Issue 7

## Issue 9 - Add profile customization uploads

Objective:
Let users personalize their profile appearance with uploaded media.

Status tracker:
- [ ] Complete
- [x] In progress
- [ ] Not started

Checklist:
- Add background image upload.
- Add avatar upload or selection if desired.
- Validate file type, size, and storage path.
- Add profile preview behavior after upload.

Acceptance criteria:
- Users can upload a background image successfully.
- Uploaded media appears on the profile page.

Depends on:
- Issue 3

## Issue 10 - Add follow relationships

Objective:
Track who follows whom for social feed generation.

Status tracker:
- [ ] Complete
- [ ] In progress
- [x] Not started

Checklist:
- Add follow/unfollow persistence model.
- Add follow counts or relationship queries.
- Prevent duplicate follow records.
- Support blocking or privacy rules later if needed.

Acceptance criteria:
- A user can follow and unfollow another account.
- Follow data can be queried efficiently for the feed.

Depends on:
- Issue 3

## Issue 11 - Build social feed timeline

Objective:
Show a timeline of reviews and relevant updates from followed accounts.

Status tracker:
- [ ] Complete
- [x] In progress
- [ ] Not started

Checklist:
- Build feed query for both global and followed-accounts views.
- Render reviews, notes, posts, and lists in chronological order.
- Add empty-state and loading-state behavior.
- Make feed items link back to author profiles and content pages.
- Ensure feed events are generated only on publish when visibility is public/followers-visible.
- Ensure drafts/private content/quiet-save operations do not create feed events.
- Implement `feed_event` as target pointer; resolve visibility from target at read time.
- Do not trust feed rows alone for privacy decisions.

Acceptance criteria:
- The feed shows posts from followed users only.
- The feed updates as new reviews are created.
- Feed privacy remains correct even if stale feed rows exist.

Depends on:
- Issue 6
- Issue 10

## Issue 12 - Add search and discovery

Objective:
Make it easier to find people, lists, and reviews.

Status tracker:
- [ ] Complete
- [ ] In progress
- [x] Not started

Checklist:
- Add user search.
- Add list search.
- Add review search.
- Add category filters and sorting options.

Acceptance criteria:
- Search returns useful results across core content types.
- Discovery works without breaking the main feed or profile flows.

Depends on:
- Issue 4
- Issue 5
- Issue 11

## Issue 13 - Add privacy and moderation controls

Objective:
Define what is public, private, and follow-only content.

Status tracker:
- [ ] Complete
- [ ] In progress
- [ ] Not started

Checklist:
- Add public/private profile settings.
- Add visibility settings for reviews, lists, notes, and posts.
- Add content hiding or deletion workflow.
- Add moderation hooks if the app grows into a community product.
- Add owner control toggles to disable comments on posts.
- Add owner comment deletion controls on post comment threads.

Acceptance criteria:
- Users can control content visibility.
- Hidden or private content does not leak into public pages or feeds.

Depends on:
- Issue 3
- Issue 6
- Issue 7

## Issue 14 - Add tests for core flows

Objective:
Cover the most important user paths before expanding features.

Status tracker:
- [ ] Complete
- [x] In progress
- [ ] Not started

Checklist:
- Add auth mode tests.
- Add profile creation and rendering tests.
- Add list creation and category styling tests.
- Add review posting and feed visibility tests.
- Add follow/unfollow tests.

Acceptance criteria:
- Core flows are covered with focused tests.
- Tests fail for broken profile, feed, or visibility behavior.

Depends on:
- Issue 1
- Issue 2
- Issue 4
- Issue 5
- Issue 6
- Issue 7
- Issue 10
- Issue 11

## Issue 15 - Prepare deployment and docs

Objective:
Document how NEERA runs standalone and inside the shared ecosystem.

Status tracker:
- [ ] Complete
- [x] In progress
- [ ] Not started

Checklist:
- Document local setup.
- Document environment variables.
- Document storage requirements for uploads.
- Document standalone and SSO deployment modes.
- Add deployment notes for the shared stack.

Acceptance criteria:
- Another developer can run NEERA from the docs.
- Deployment instructions are clear for both local and shared-auth setups.

Depends on:
- Issue 1
- Issue 2
- Issue 9
- Issue 14

## Issue 16 - Add category taxonomy and seeded catalog

Objective:
Seed and normalize day-1 catalog data for book, song, arts, and films so users can review immediately.

Status tracker:
- [ ] Complete
- [x] In progress
- [ ] Not started

Checklist:
- Create canonical category enum/taxonomy: book, song, arts, films.
- Add seeded item dataset per category with minimal metadata contract.
- Add seeding command(s) and idempotent behavior.
- Distinguish seeded/trusted items from user-submitted items at persistence level.

Acceptance criteria:
- Fresh setup contains seeded items across all categories.
- Users can create reviews on seeded items without adding metadata.

Depends on:
- Issue 1
- Issue 6

## Issue 17 - Build item details page (2-column)

Objective:
Build the item destination page with full review and metadata surfaces.

Status tracker:
- [ ] Complete
- [x] In progress
- [ ] Not started

Checklist:
- Implement left column (65%) and right column (35%) layout.
- Add left sections: item header, action row, related lists preview, review stream.
- Add right sections: ratings box, your rating, metadata panel, tags, discussions.
- Add item-type-specific fields (author/director/creator, year, length/page count).

Acceptance criteria:
- Every item has a dedicated page using the same section contract.
- Ratings, metadata, and review previews are visible and coherent on desktop and mobile.

Depends on:
- Issue 6
- Issue 7
- Issue 16

## Issue 18 - Add user-submitted item contribution flow

Objective:
Allow users to create missing catalog items by submitting metadata and a review together.

Status tracker:
- [ ] Complete
- [x] In progress
- [ ] Not started

Checklist:
- Add item contribution form in item creation/review flow.
- Persist metadata confidence score for user-submitted entries.
- Render per-field confidence badges (red/yellow/green) in metadata panel.
- Keep description intentionally empty by default for user-submitted entries unless curated later.

Acceptance criteria:
- A user can submit a missing item and first review in one action.
- Confidence signals appear only for user-submitted entries (not seeded items).

Depends on:
- Issue 16
- Issue 17

## Issue 19 - Add notes and posts content types

Objective:
Introduce notes/posts creation and rendering across profile and item discussion surfaces.

Status tracker:
- [ ] Complete
- [ ] In progress
- [ ] Not started

Checklist:
- Add note and post persistence models.
- Add create/edit/delete flows for notes and posts.
- Add markdown support for long-form notes.
- Add mention/reference support via @ linking across supported target types.
- Add profile tabs and feed inclusion for notes/posts.
- Enforce notes as non-commentable entities.
- Add post body character limit (500).
- Add "appeared in <n> places" support for lists/notes/reviews.

Acceptance criteria:
- Users can create notes/posts and reference items.
- Notes/posts appear on profile pages and in feed based on visibility.
- Notes are discussed via posts that reference them.

Depends on:
- Issue 4
- Issue 11

## Issue 20 - Add reactions and post-only comments

Objective:
Enable lightweight social interaction on reviews, lists, notes, and posts.

Status tracker:
- [ ] Complete
- [ ] In progress
- [ ] Not started

Checklist:
- Add reaction model with fields: `id`, `user_id`, `target_type`, `target_id`, `reaction_type`.
- Use `reaction_type=heart` for v1 while keeping reaction model extensible.
- Add reaction endpoints for reviews/lists/notes/posts.
- Add non-polymorphic post comment model with flat threading.
- Add post comment statuses: `visible`, `deleted_by_author`, `deleted_by_post_owner`, `removed_by_moderator`.
- Add post owner controls for comment deletion and comment disable toggle.

Acceptance criteria:
- Users can react on reviews/notes/lists/posts.
- Comments are supported only on posts.
- Post comment threads remain flat and moderation controls work correctly.

Depends on:
- Issue 6
- Issue 7
- Issue 19

## Issue 21 - Redesign profile page and highlights

Objective:
Implement the richer identity-first profile layout and pinned highlights behavior.

Status tracker:
- [ ] Complete
- [x] In progress
- [ ] Not started

Checklist:
- Add hero image with fade merge and avatar overlay treatment.
- Add profile meta block (name, user id, bio, links, location, join date).
- Add strip counters for lists/notes/friends.
- Add tabs for lists, reviews, notes, and feed with required card treatments.
- Add pin/highlight controls for lists/reviews/notes/posts and top-order rendering.

Acceptance criteria:
- Profile page renders full hierarchy and tabs.
- Users can pin multiple entries and see them prioritized.

Depends on:
- Issue 3
- Issue 4
- Issue 5
- Issue 19

## Issue 22 - Expand feed behavior and visibility propagation

Objective:
Implement deterministic feed generation with strict visibility semantics.

Status tracker:
- [ ] Complete
- [x] In progress
- [ ] Not started

Checklist:
- Add global feed plus followed-people feed modes.
- Add feed event generation only on public/followers-visible publish.
- Skip feed events for drafts, private content, and quiet-save updates.
- Exclude private items from non-owner feed contexts.
- Preserve chronological ordering and prevent duplicate event fan-out.
- Resolve visibility from target at read time (`feed_event` is pointer only).

Acceptance criteria:
- Feed modes return expected content consistently.
- Private content never appears in public/global/following feeds.
- Feed visibility remains correct even with stale feed rows.

Depends on:
- Issue 10
- Issue 11
- Issue 13
- Issue 19

## Issue 23 - Add mention graph and appearance counters

Objective:
Track cross-content references and expose appearance counts for lists, notes, and reviews.

Status tracker:
- [ ] Complete
- [ ] In progress
- [ ] Not started

Checklist:
- Add mention edges between source and target entities.
- Support valid routes:
  - post -> review, note, list, post
  - note -> note
  - review -> note
- Reject unsupported mention routes via validation.
- Add aggregate "appeared in <n> places" counters on list/note/review surfaces.
- Keep counters consistent on create/edit/delete of mention-bearing content.

Acceptance criteria:
- Valid mentions resolve and invalid links are rejected.
- Appearance counters are stable and auditable.

Depends on:
- Issue 19
- Issue 20
- Issue 22

## Bottlenecks and Issues to Watch

1. Data model sprawl and polymorphic complexity
- Risk: reactions/feed events/mentions that target multiple entity types can create brittle query logic.
- Mitigation: standardize shared target contracts early (type + id), add strict DB constraints, and centralize serializers.

2. Privacy leakage through feed/event fan-out
- Risk: private reviews/notes/posts/lists can leak via cached feed rows or stale denormalized tables.
- Mitigation: enforce visibility checks at read time plus write-time invalidation; add regression tests around privacy toggles.

3. Confidence-score UX trust gap
- Risk: users may misinterpret red/yellow/green confidence as moderation verdicts rather than metadata confidence.
- Mitigation: add clear tooltip copy and only show confidence treatment on user-submitted items.

4. Seed data quality and taxonomy drift
- Risk: inconsistent fields across categories can break item-page rendering.
- Mitigation: define per-category minimum schema contract and validate seed payloads in CI.

5. Performance on item pages and profile tabs
- Risk: item page loads (reviews + ratings + list references + discussions) can turn into N+1 query patterns.
- Mitigation: prefetch aggressively, add pagination defaults, and capture baseline query counts in tests.

6. Comment moderation scope creep
- Risk: post comment status transitions may be handled inconsistently across API and UI.
- Mitigation: enforce one status transition map and one policy layer for post comments.

7. Feed spam and noisy auto-posting
- Risk: auto-posting every update may overload follower feeds.
- Mitigation: publish-only events, quiet-save mode, and event dedupe/coalescing windows.

8. Category taxonomy drift
- Risk: unclear category rules create tagging and search inconsistency.
- Mitigation: document canonical examples and allowed metadata fields before seed/import work.