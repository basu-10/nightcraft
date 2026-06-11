# NEERA (app-artsy) Project Idea and Product Blueprint

## 1. Product Summary

NEERA is a social review and curation platform for creative media. Users can review items, build lists, write notes, and post updates.

Primary review categories:

- Book
- Song
- Arts
- Films

Key principle:

- Users should be able to contribute from day 1, even when an item does not yet exist in the database.

## 2. Core Experience Goals

- Start useful immediately with seeded catalog data across all categories.
- Let users contribute missing items with metadata plus review in one flow.
- Make each item feel like a destination page with reviews, ratings, metadata, tags, and discussion.
- Make profile pages identity-forward and social, with highlights and feed-like activity.
- Support creators and curators with lists, notes, posts, and reactions.
- Make posts the primary social interaction layer (discussion, mentions, and feed delivery).

## 2.1 Current Implementation Snapshot (May 2026)

Implemented foundations:

- Auth adapters support both local and shared-SSO mode.
- Profiles, reviews, lists, list items, notes, and feed-event pointer storage exist.
- Catalog seeding and browse experience exist (`seed-catalog`, `/items`, `/items/<id>`).
- Search-first review composition exists (`/reviews/new`) with create-missing-book support.
- Published non-private reviews emit `feed_event` rows; profile feed resolves event targets at read time.

Still pending for the product contract:

- Follow graph and global-vs-following feed modes.
- Notes/posts social loop (mentions, reactions, post-only comments).
- Per-field confidence badges for user-submitted metadata.
- Typed-list enforcement plus mixed-list note/post composition rules.
- Search/discovery polish and broader privacy/moderation coverage.

## 3. Content Model

Primary content types:

- Item (book/song/arts/films)
- Review
- List
- List item
- Note
- Post
- Post comment
- Reaction (heart/like)
- Tag
- Feed event

List types:

- Book
- Song
- Arts
- Films
- Mixed

Mixed list behavior:

- Can contain items from multiple categories.
- Can include works, notes, and posts in one ordered sequence.

Typed list constraints:

- Book list contains only book works.
- Film list contains only film works.
- Song list contains only song works.
- Art list contains only art works.

Mention/reference behavior:

- Post can @ reference posts, reviews, notes, and lists.
- Note can @ reference notes.
- Review can @ reference notes.

Appeared count behavior:

- Each list, note, and review displays "appeared in <n> places".
- The count is incremented when the entity is referenced from allowed surfaces (for example, a note referenced by a post).

## 4. Catalog and Seeding Strategy

Each category starts with seeded items so users can review immediately.

Seeded item behavior:

- Trusted metadata.
- Standard item display.
- No confidence badges on metadata fields.

User-submitted item behavior:

- User enters metadata and review in one creation flow.
- Description area remains empty by default to signal uncertainty.
- Show confidence score badge at item level.
- Show color badges per metadata field to indicate confidence quality.

Metadata confidence color proposal:

- Green: high confidence
- Yellow: medium confidence
- Red: low confidence

Important distinction:

- Metadata confidence badges appear only for user-submitted items, not for seeded/trusted catalog items.

## 5. Item Page Specification

Two-column layout:

- Left column: 65% width (primary content)
- Right column: 35% width (summary and utilities)

### Left Column (65%)

Section 1: Item header container

- Image
- Title
- Author/Director/Creator
- Year
- Page count or length
- Brief description (empty for user-submitted items by default)
- Confidence score badge (only for user-submitted items)

Section 2: Action row (right-aligned within left column)

- Write a review
- Contribute metadata
- Bookmark icon

Section 3: Related lists preview

- Show up to 5 list names containing the item
- Show more button

Section 4: Reviews stream

- List of reviews with preview content
- Each review supports hearts
- Reviews do not have comments

### Right Column (35%)

Section 1: Ratings box (square)

- Large aggregate rating
- Rating breakdown below

Section 2: Your rating

- Current user rating summary
- Link to edit rating page

Section 3: Metadata panel

- Full metadata values
- For user-submitted items, show per-field confidence color badges (red/yellow/green)

Section 4: Tags

- Item tags

Section 5: Discussions

- Posts that reference the item with @ mention

## 6. Social Actions and Interaction Rules

Users can react (heart for now) on:

- Reviews
- Lists
- Notes
- Posts

Reaction storage model (internal):

- `id`
- `user_id`
- `target_type`
- `target_id`
- `reaction_type`

V1 reaction type:

- `reaction_type=heart`

UI presentation:

- `❤️ 128`

Interaction matrix:
| Entity | Hearts | Comments | Can Be @ Linked From |
| --- | --- | --- | --- |
| Review | Yes | No | Post |
| Note | Yes | No | Post, Note, Review |
| List | Yes | No | Post |
| Post | Yes | Yes | Post |

Post behavior:

- Body text
- Visibility
- Mentions
- Reactions
- Feed delivery
- Comments enabled/disabled by post owner
- Character limit: 500

Comment model:

- Only posts have comments.
- Flat comments only (no nesting in v1).
- Comment status values:
  - visible
  - deleted_by_author
  - deleted_by_post_owner
  - removed_by_moderator
- Post owner controls:
  - Delete comments
  - Disable comments

Notes behavior:

- Notes are long-form markdown content (article-like).
- Notes allow reactions but do not allow comments.
- Discussion happens through posts that reference notes.
- Referenced notes increment their "appeared in <n> places" count.

## 7. User Profile Page Specification

Top hero section:

- Facebook-like hero image
- Lower fade merge into page background
- Circular profile image overlaid on left side of hero
- Right of profile image:
  - Name
  - User ID
  - Bio
  - Links
  - Location
  - Join date

Profile strip below hero:

- Followers
- Following
- Pencil edit button
- pills for total review count, Total list count, Total note count, Total post count

Highlights block:
users select lists or review or notes to pin as highlights on their profile. These are curated by the user and can be changed at any time. They are a way for users to showcase their best content and express their identity through their profile.

Tabbed content:

- Lists (rectangular card UI)
- Reviews (square card UI)
- Notes (square card UI)
- Feed (chronological)
- Bookmarks(only visible to the profile owner)

Creation flow:

- Each tab exposes create action relevant to that content type.

Pin/highlight behavior:

- Users can pin multiple entries.
- Pinned entries move to top in their page section.
- Supported for lists, reviews, notes, posts.

## 8. List Experience

List card (overview):

- Square-ish style
- Title
- Description
- Item thumbnail strip
- "+ <n> more" indicator

List detail page:

- Full title and description (unclipped)
- Full item list
- Owner-only controls visible only to list owner

List item enhancement:

- If list includes item user has reviewed, allow toggle to show "My Review" link beside that item.

Owner controls placement:

- Owner admin controls and settings (public/private, highlight toggle, etc.) appear below review and before interaction controls where applicable.

Mixed lists as structure-first containers:

- Mixed lists can naturally hold a sequence of notes (for example, Chapter 1, Chapter 2, Chapter 3).
- This is enabled by the generic list-item model; the UI should not introduce a separate "novel" feature label.

Lists as expressive moodboards:

- Mixed lists can combine books, films, songs, art, notes, and posts to represent a taste map rather than only a review index.

## 9. Feed Design

Feed modes:

- Global feed
- Followed-people feed

Feed content types:

- Recent reviews
- Posts
- Notes
- Lists

Auto-post behavior:

- Publishing public or followers-visible review/post/note/list creates a feed event.
- Draft creation does not create a feed event.
- Private content does not create a public feed event.
- Quiet save does not create a feed event.

Visibility behavior:

- Public content appears in visible feed contexts.
- Private content functions as draft/private storage and does not appear publicly.

Feed-event privacy contract:

- `feed_event` points to target content.
- Target visibility is checked at read time.
- Do not trust feed rows alone for privacy decisions.

Primary reasons for public/private switch:

- Draft workflow
- Spam and visibility control

## 10. Permissions and Visibility (v1)

Ownership:

- Owners can edit/delete their own content.
- Owner-only admin controls are visible only to owners.

Visibility:

- Every review/post/note/list supports private/public state.
- Visibility can be changed after creation.

Comment controls:

- Comment controls exist only for posts.
- Post owner can moderate by deleting comments or disabling comments entirely.

## 11. Suggested MVP Scope

Phase 1 (foundation):

- Category taxonomy (book/song/arts/films)
- Seeded catalog data for all categories
- Item page with two-column layout and review list
- Review create/read/update/delete
- User-submitted item flow (metadata + review)

Phase 2 (social core):

- Lists (typed + mixed)
- Notes and posts
- Reactions (heart in v1) on reviews/lists/notes/posts
- Comments on posts only with owner moderation controls

Phase 3 (profile + feed):

- Full profile page layout and highlight pins
- Global feed and followed feed
- Auto-post activity stream with visibility rules

Phase 4 (quality and trust):

- Metadata confidence scoring for user-submitted items
- Field-level confidence badges in metadata panel
- Improved ranking/discovery and anti-spam tuning

## 12. Open Decisions

- Confidence score computation formula and thresholds.
- Follow graph rules (private accounts, approval flow, blocking).
- Rate limits and anti-spam thresholds for automated feed events.
- Whether comments should support edits in v1.

## 13. Success Criteria

- New user can review seeded items in under 2 minutes.
- New item contribution flow can publish item + review in one pass.
- Item pages become the core engagement surface (reviews, ratings, lists, discussion).
- Users can maintain active profiles with lists, notes, reviews, and posts.
- Public/private controls keep feed quality manageable while preserving drafts.

## 14. Recommended Next Course of Action (No Server Setup)

1. Complete item-linked contribution flow before adding new social entities.

- Expand create-and-review flow beyond books to songs/films/arts.
- Add per-field confidence badge rendering for user-submitted metadata.

2. Finish item page contract so each item page is fully useful.

- Implement related lists preview data, richer ratings breakdown, and discussion placeholders backed by real queries.

3. Build social primitives in this order: follow graph -> feed modes -> post/note reactions/comments.

- Implement follow/unfollow persistence and queries.
- Add global and following feeds using the pointer-based visibility-read contract.
- Add heart reactions and post-only flat comments with owner moderation toggles.

4. Lock privacy semantics with tests before widening discovery.

- Add coverage for draft/private/followers visibility transitions.
- Add regression tests ensuring stale feed rows cannot leak private targets.

5. Finalize discovery and taxonomy polish after social/privacy contracts stabilize.

- Category styling system and typed/mixed list rule enforcement.
- Unified search for users, lists, reviews, items, and notes/posts.

---
