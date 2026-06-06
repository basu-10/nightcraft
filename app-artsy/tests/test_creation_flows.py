from io import BytesIO
import os

import pytest

from neera import create_app
from neera.extensions import db
from neera.models import (
    NeeraArtMetadata,
    NeeraBookMetadata,
    NeeraFilmMetadata,
    NeeraItem,
    NeeraList,
    NeeraListItem,
    NeeraNote,
    NeeraSongMetadata,
    FeedEvent,
    LocalCredential,
    Review,
    UserProfile,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()

if not TEST_DATABASE_URL:
    pytest.skip("TEST_DATABASE_URL is required for PostgreSQL-backed tests.", allow_module_level=True)


def _build_test_app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "AUTH_MODE": "local",
            "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URL,
        }
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
    return app


def _create_local_user(username="creator", password="pw123"):
    user = LocalCredential(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    profile = user.ensure_profile()
    db.session.flush()
    return user, profile


def _login(client, username="creator", password="pw123"):
    response = client.post(
        "/auth/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code in (301, 302, 303)


def test_login_page_shows_admin_portal_handoff_link(tmp_path):
    app = _build_test_app(tmp_path)
    client = app.test_client()

    response = client.get("/auth/login")
    assert response.status_code == 200

    page = response.get_data(as_text=True)
    assert "Admin Portal Login" in page
    assert "/auth/login?next=/admin" in page


def test_profile_page_hides_composer_for_non_owner(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _user, profile = _create_local_user(username="publicviewer")
        username = profile.username
        db.session.commit()

    client = app.test_client()
    response = client.get(f"/u/{username}")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Create a list" not in page
    assert "Publish a review" not in page
    assert "Bookmarks" not in page



def test_create_list_persists_and_renders_on_me(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user()
        db.session.commit()

    client = app.test_client()
    _login(client)

    response = client.post(
        "/me/lists",
        data={
            "title": "Rainy Day Films",
            "category": "films",
            "description": "Low light and quiet heartbreak.",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Rainy Day Films" in page
    assert "List created." in page

    with app.app_context():
        created = NeeraList.query.filter_by(title="Rainy Day Films").first()
        assert created is not None
        assert created.category == "films"
        assert created.visibility == "public"
        assert created.item_count == 0



def test_create_review_persists_and_renders_on_me(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user()
        db.session.commit()

    client = app.test_client()
    _login(client)

    response = client.post(
        "/me/reviews",
        data={
            "subject": "Blue by Joni Mitchell",
            "category": "songs",
            "rating": "5",
            "body": "Still one of the most emotionally precise albums ever made.",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Blue by Joni Mitchell" in page
    assert "Review published." in page

    with app.app_context():
        created = Review.query.filter_by(subject="Blue by Joni Mitchell").first()
        assert created is not None
        assert created.rating == 5
        assert created.category == "songs"


def test_review_search_shows_exact_and_similar_states(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user()
        exact = NeeraItem(
            category="book",
            title="The Hobbit",
            creator_display_name="J.R.R. Tolkien",
            image_url="https://example.com/hobbit.jpg",
            description="A classic adventure.",
            source_type="seeded",
            source_id="hobbit",
            is_user_submitted=False,
            metadata_confidence=1.0,
        )
        similar = NeeraItem(
            category="book",
            title="The Book That Didn't Exist",
            creator_display_name="Author B",
            image_url="https://example.com/exists.jpg",
            description="Close title.",
            source_type="seeded",
            source_id="similar-1",
            is_user_submitted=False,
            metadata_confidence=1.0,
        )
        db.session.add_all([exact, similar])
        db.session.flush()
        db.session.add_all(
            [
                NeeraBookMetadata(work_id=exact.id, author="J.R.R. Tolkien", year=1937),
                NeeraBookMetadata(work_id=similar.id, author="Author B", year=2020),
            ]
        )
        db.session.commit()

    client = app.test_client()
    _login(client)

    exact_response = client.get("/reviews/new?category=book&q=The Hobbit")
    assert exact_response.status_code == 200
    exact_page = exact_response.get_data(as_text=True)
    assert "Exact match found" in exact_page
    assert "Review this" in exact_page

    similar_response = client.get("/reviews/new?category=book&q=The Book That Does Not Exist")
    assert similar_response.status_code == 200
    similar_page = similar_response.get_data(as_text=True)
    assert "We couldn't find an exact match." in similar_page
    assert "None of these. Create new book" in similar_page


def test_create_new_book_then_publish_review_creates_feed_event(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user()
        db.session.commit()

    client = app.test_client()
    _login(client)

    create_response = client.post(
        "/reviews/new/book",
        data={
            "title": "The Book That Does Not Exist",
            "author": "Some Author",
        },
        follow_redirects=True,
    )
    assert create_response.status_code == 200
    create_page = create_response.get_data(as_text=True)
    assert "Step 2: Write your review" in create_page

    with app.app_context():
        book = NeeraItem.query.filter_by(title="The Book That Does Not Exist").first()
        assert book is not None
        assert book.is_user_submitted is True
        assert book.metadata_confidence == 0.35

    publish_response = client.post(
        "/reviews/new/compose",
        data={
            "work_id": str(book.id),
            "subject": book.title,
            "category": "book",
            "rating": "4",
            "review_title": "A strange but interesting read",
            "body": "Worth discovering early.",
            "tags": "mysterious, promising",
            "visibility": "public",
            "status": "published",
        },
        follow_redirects=True,
    )
    assert publish_response.status_code == 200
    publish_page = publish_response.get_data(as_text=True)
    assert "Review published." in publish_page
    assert "Your review is highlighted here." in publish_page
    assert "This book page is new." in publish_page

    with app.app_context():
        review = Review.query.filter_by(work_id=book.id).first()
        assert review is not None
        assert review.review_title == "A strange but interesting read"
        assert review.status == "published"
        assert review.visibility == "public"
        feed_event = FeedEvent.query.filter_by(target_type="review", target_id=review.id).first()
        assert feed_event is not None


def test_create_new_book_duplicate_warning_and_draft_no_feed_event(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user()
        existing = NeeraItem(
            category="book",
            title="The Book That Does Not Exist",
            creator_display_name="S. Author",
            image_url="https://example.com/dup.jpg",
            description="Existing book.",
            source_type="seeded",
            source_id="dup-1",
            is_user_submitted=False,
            metadata_confidence=1.0,
        )
        db.session.add(existing)
        db.session.flush()
        db.session.add(NeeraBookMetadata(work_id=existing.id, author="S. Author", year=2020))
        db.session.commit()

    client = app.test_client()
    _login(client)

    warning_response = client.post(
        "/reviews/new/book",
        data={"title": "The Book That Does Not Exist"},
        follow_redirects=True,
    )
    assert warning_response.status_code == 200
    warning_page = warning_response.get_data(as_text=True)
    assert "Before you create this, check these possible matches:" in warning_page
    assert "Use existing" in warning_page
    assert "Create new anyway" in warning_page

    create_response = client.post(
        "/reviews/new/book",
        data={
            "title": "The Book That Does Not Exist Again",
            "confirm_create_new": "1",
        },
        follow_redirects=True,
    )
    assert create_response.status_code == 200
    assert "Step 2: Write your review" in create_response.get_data(as_text=True)

    with app.app_context():
        created_book = NeeraItem.query.filter_by(title="The Book That Does Not Exist Again").first()
        assert created_book is not None
        assert created_book.metadata_confidence == 0.2

    draft_response = client.post(
        "/reviews/new/compose",
        data={
            "work_id": str(created_book.id),
            "subject": created_book.title,
            "category": "book",
            "rating": "5",
            "review_title": "Saving for later",
            "body": "",
            "visibility": "private",
            "status": "draft",
        },
        follow_redirects=True,
    )
    assert draft_response.status_code == 200
    assert "Draft saved." in draft_response.get_data(as_text=True)

    with app.app_context():
        review = Review.query.filter_by(work_id=created_book.id).first()
        assert review is not None
        assert review.status == "draft"
        assert review.visibility == "private"
        assert FeedEvent.query.filter_by(target_type="review", target_id=review.id).first() is None



def test_create_list_item_orders_entries_and_updates_count(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _user, profile = _create_local_user()
        Neera_list = NeeraList(
            profile_id=profile.id,
            category="books",
            title="Shelf",
            description="Favorites",
            item_count=1,
        )
        db.session.add(Neera_list)
        db.session.flush()
        db.session.add(
            NeeraListItem(
                list_id=Neera_list.id,
                position=1,
                title="Existing Book",
                creator_name="Author A",
            )
        )
        db.session.commit()
        list_id = Neera_list.id

    client = app.test_client()
    _login(client)

    response = client.post(
        f"/me/lists/{list_id}/items",
        data={
            "title": "New Book",
            "creator_name": "Author B",
            "notes": "Read next",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "New Book" in page
    assert "List item added." in page

    with app.app_context():
        stored_list = NeeraList.query.get(list_id)
        items = NeeraListItem.query.filter_by(list_id=list_id).order_by(NeeraListItem.position.asc()).all()
        assert stored_list.item_count == 2
        assert [item.title for item in items] == ["Existing Book", "New Book"]
        assert [item.position for item in items] == [1, 2]


def test_edit_and_delete_list(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _user, profile = _create_local_user()
        Neera_list = NeeraList(profile_id=profile.id, category="books", title="Shelf", description="Old")
        db.session.add(Neera_list)
        db.session.commit()
        list_id = Neera_list.id

    client = app.test_client()
    _login(client)

    edit_response = client.post(
        f"/me/lists/{list_id}/edit",
        data={"title": "Updated Shelf", "category": "films", "description": "New mood"},
        follow_redirects=True,
    )
    assert edit_response.status_code == 200
    assert "List updated." in edit_response.get_data(as_text=True)

    with app.app_context():
        updated = db.session.get(NeeraList, list_id)
        assert updated.title == "Updated Shelf"
        assert updated.category == "films"
        assert updated.description == "New mood"

    delete_response = client.post(f"/me/lists/{list_id}/delete", follow_redirects=True)
    assert delete_response.status_code == 200
    assert "List deleted." in delete_response.get_data(as_text=True)

    with app.app_context():
        assert db.session.get(NeeraList, list_id) is None


def test_edit_and_delete_review(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _user, profile = _create_local_user()
        review = Review(profile_id=profile.id, category="books", subject="Old", body="Before", rating=2)
        db.session.add(review)
        db.session.commit()
        review_id = review.id

    client = app.test_client()
    _login(client)

    edit_response = client.post(
        f"/me/reviews/{review_id}/edit",
        data={"subject": "New", "category": "songs", "rating": "5", "body": "After"},
        follow_redirects=True,
    )
    assert edit_response.status_code == 200
    assert "Review updated." in edit_response.get_data(as_text=True)

    with app.app_context():
        updated = db.session.get(Review, review_id)
        assert updated.subject == "New"
        assert updated.category == "songs"
        assert updated.rating == 5
        assert updated.body == "After"

    delete_response = client.post(f"/me/reviews/{review_id}/delete", follow_redirects=True)
    assert delete_response.status_code == 200
    assert "Review deleted." in delete_response.get_data(as_text=True)

    with app.app_context():
        assert db.session.get(Review, review_id) is None


def test_reorder_and_delete_list_items(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _user, profile = _create_local_user()
        Neera_list = NeeraList(profile_id=profile.id, category="books", title="Shelf", description="Favorites", item_count=3)
        db.session.add(Neera_list)
        db.session.flush()
        db.session.add_all(
            [
                NeeraListItem(list_id=Neera_list.id, position=1, title="First"),
                NeeraListItem(list_id=Neera_list.id, position=2, title="Second"),
                NeeraListItem(list_id=Neera_list.id, position=3, title="Third"),
            ]
        )
        db.session.commit()
        list_id = Neera_list.id
        second_item_id = NeeraListItem.query.filter_by(list_id=list_id, title="Second").first().id
        first_item_id = NeeraListItem.query.filter_by(list_id=list_id, title="First").first().id

    client = app.test_client()
    _login(client)

    move_response = client.post(
        f"/me/lists/{list_id}/items/{second_item_id}/move",
        data={"direction": "up"},
        follow_redirects=True,
    )
    assert move_response.status_code == 200
    assert "List item reordered." in move_response.get_data(as_text=True)

    with app.app_context():
        items = NeeraListItem.query.filter_by(list_id=list_id).order_by(NeeraListItem.position.asc()).all()
        assert [item.title for item in items] == ["Second", "First", "Third"]

    delete_response = client.post(
        f"/me/lists/{list_id}/items/{first_item_id}/delete",
        follow_redirects=True,
    )
    assert delete_response.status_code == 200
    assert "List item deleted." in delete_response.get_data(as_text=True)

    with app.app_context():
        items = NeeraListItem.query.filter_by(list_id=list_id).order_by(NeeraListItem.position.asc()).all()
        stored_list = db.session.get(NeeraList, list_id)
        assert [item.title for item in items] == ["Second", "Third"]
        assert [item.position for item in items] == [1, 2]
        assert stored_list.item_count == 2


def test_public_lists_page_renders_profile_lists(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _user, profile = _create_local_user(username="listowner")
        db.session.add(
            NeeraList(
                profile_id=profile.id,
                category="books",
                title="Public Shelf",
                description="Open list",
                item_count=0,
            )
        )
        db.session.commit()

    client = app.test_client()
    response = client.get("/u/listowner/lists")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Public Shelf" in page
    assert "listowner" in page


def test_my_lists_requires_authentication(tmp_path):
    app = _build_test_app(tmp_path)
    client = app.test_client()

    response = client.get("/me/lists", follow_redirects=False)
    assert response.status_code in (301, 302, 303, 307, 308)
    assert "/auth/login" in response.headers.get("Location", "")


def test_my_lists_renders_for_authenticated_owner(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user()
        db.session.commit()

    client = app.test_client()
    _login(client)

    response = client.get("/me/lists")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Create a list" in page
    assert "class=\"active\">Lists" in page


def test_owner_profile_renders_bookmarks_tab(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user()
        db.session.commit()

    client = app.test_client()
    _login(client)

    response = client.get("/me")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Drafts" in page
    assert "Bookmarks" in page


def test_public_profile_hides_private_lists_and_reviews_from_main_tabs(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _user, profile = _create_local_user(username="owner")
        db.session.add_all(
            [
                NeeraList(
                    profile_id=profile.id,
                    category="books",
                    title="Public Shelf",
                    description="Shown publicly",
                    visibility="public",
                ),
                NeeraList(
                    profile_id=profile.id,
                    category="books",
                    title="Secret Shelf",
                    description="Hidden",
                    visibility="private",
                ),
                Review(
                    profile_id=profile.id,
                    category="books",
                    subject="Public Review",
                    body="Visible",
                    rating=4,
                    visibility="public",
                    status="published",
                ),
                Review(
                    profile_id=profile.id,
                    category="books",
                    subject="Private Review",
                    body="Hidden",
                    rating=4,
                    visibility="private",
                    status="published",
                ),
                Review(
                    profile_id=profile.id,
                    category="books",
                    subject="Draft Review",
                    body="Hidden draft",
                    rating=4,
                    visibility="public",
                    status="draft",
                ),
            ]
        )
        db.session.commit()

    client = app.test_client()

    reviews_response = client.get("/u/owner")
    assert reviews_response.status_code == 200
    reviews_page = reviews_response.get_data(as_text=True)
    assert "Public Review" in reviews_page
    assert "Private Review" not in reviews_page
    assert "Draft Review" not in reviews_page
    assert "Drafts" not in reviews_page

    lists_response = client.get("/u/owner/lists")
    assert lists_response.status_code == 200
    lists_page = lists_response.get_data(as_text=True)
    assert "Public Shelf" in lists_page
    assert "Secret Shelf" not in lists_page


def test_drafts_route_requires_owner_and_shows_private_content(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _user, owner_profile = _create_local_user(username="owner")
        _create_local_user(username="outsider")
        private_list = NeeraList(
            profile_id=owner_profile.id,
            category="books",
            title="Secret Shelf",
            description="Hidden",
            visibility="private",
        )
        private_review = Review(
            profile_id=owner_profile.id,
            category="books",
            subject="Private Review",
            body="Hidden",
            rating=5,
            visibility="private",
            status="published",
        )
        draft_review = Review(
            profile_id=owner_profile.id,
            category="books",
            subject="Draft Review",
            body="Later",
            rating=3,
            visibility="public",
            status="draft",
        )
        db.session.add_all([private_list, private_review, draft_review])
        db.session.commit()

    client = app.test_client()
    _login(client, username="outsider")

    forbidden_response = client.get("/u/owner/drafts")
    assert forbidden_response.status_code == 404

    client.post("/auth/logout")
    _login(client, username="owner")

    allowed_response = client.get("/u/owner/drafts")
    assert allowed_response.status_code == 200
    drafts_page = allowed_response.get_data(as_text=True)
    assert "Drafts &amp; Private" in drafts_page or "Drafts & Private" in drafts_page
    assert "Secret Shelf" in drafts_page
    assert "Private Review" in drafts_page
    assert "Draft Review" in drafts_page


def test_editing_private_content_from_drafts_redirects_back_to_drafts(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _user, profile = _create_local_user(username="owner")
        Neera_list = NeeraList(
            profile_id=profile.id,
            category="books",
            title="Secret Shelf",
            description="Hidden",
            visibility="private",
        )
        review = Review(
            profile_id=profile.id,
            category="books",
            subject="Private Review",
            body="Hidden",
            rating=4,
            visibility="private",
            status="published",
        )
        db.session.add_all([Neera_list, review])
        db.session.commit()
        list_id = Neera_list.id
        review_id = review.id

    client = app.test_client()
    _login(client, username="owner")

    edit_list_response = client.post(
        f"/me/lists/{list_id}/edit",
        data={
            "title": "Secret Shelf",
            "category": "books",
            "description": "Now visible",
            "visibility": "public",
            "return_tab": "Drafts",
        },
        follow_redirects=True,
    )
    assert edit_list_response.status_code == 200
    assert "Drafts &amp; Private" in edit_list_response.get_data(as_text=True) or "Drafts & Private" in edit_list_response.get_data(as_text=True)

    edit_review_response = client.post(
        f"/me/reviews/{review_id}/edit",
        data={
            "subject": "Private Review",
            "category": "books",
            "rating": "4",
            "body": "Now public",
            "visibility": "public",
            "status": "published",
            "return_tab": "Drafts",
        },
        follow_redirects=True,
    )
    assert edit_review_response.status_code == 200
    review_page = edit_review_response.get_data(as_text=True)
    assert "Drafts &amp; Private" in review_page or "Drafts & Private" in review_page

    with app.app_context():
        updated_list = db.session.get(NeeraList, list_id)
        updated_review = db.session.get(Review, review_id)
        assert updated_list.visibility == "public"
        assert updated_review.visibility == "public"


def test_update_profile_header_persists_fields(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user()
        db.session.commit()

    client = app.test_client()
    _login(client)

    response = client.post(
        "/me/profile",
        data={
            "location": "Bengaluru, India",
            "profile_link": "https://linktr.ee/creator",
            "avatar_url": "https://images.example/avatar.jpg",
            "background_url": "https://images.example/hero.jpg",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Profile header updated." in page
    assert "Bengaluru, India" in page
    assert "https://linktr.ee/creator" in page

    with app.app_context():
        profile = UserProfile.query.filter_by(username="creator").first()
        assert profile.location == "Bengaluru, India"
        assert profile.profile_link == "https://linktr.ee/creator"
        assert profile.avatar_url == "https://images.example/avatar.jpg"
        assert profile.background_url == "https://images.example/hero.jpg"


def test_update_profile_header_rejects_non_http_urls(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user()
        db.session.commit()

    client = app.test_client()
    _login(client)

    response = client.post(
        "/me/profile",
        data={
            "location": "Somewhere",
            "profile_link": "javascript:alert(1)",
            "avatar_url": "https://images.example/avatar.jpg",
            "background_url": "https://images.example/hero.jpg",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "must start with http:// or https://" in page

    with app.app_context():
        profile = UserProfile.query.filter_by(username="creator").first()
        assert profile.profile_link == ""


def test_notes_and_feed_tab_routes_render_real_content(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _user, profile = _create_local_user(username="tabowner")
        public_review = Review(
            profile_id=profile.id,
            category="books",
            subject="Feed Subject",
            body="Published and public.",
            rating=5,
            visibility="public",
            status="published",
        )
        private_review = Review(
            profile_id=profile.id,
            category="books",
            subject="Hidden Feed Subject",
            body="Published but private.",
            rating=4,
            visibility="private",
            status="published",
        )
        db.session.add_all(
            [
                NeeraNote(
                    profile_id=profile.id,
                    title="Public Note",
                    body="Visible note.",
                    visibility="public",
                    status="published",
                ),
                NeeraNote(
                    profile_id=profile.id,
                    title="Private Note",
                    body="Hidden note.",
                    visibility="private",
                    status="published",
                ),
                NeeraNote(
                    profile_id=profile.id,
                    title="Draft Note",
                    body="Draft note.",
                    visibility="public",
                    status="draft",
                ),
                public_review,
                private_review,
            ]
        )
        db.session.flush()
        db.session.add_all(
            [
                FeedEvent(profile_id=profile.id, target_type="review", target_id=public_review.id),
                FeedEvent(profile_id=profile.id, target_type="review", target_id=private_review.id),
            ]
        )
        db.session.commit()
        username = profile.username

    client = app.test_client()

    notes_response = client.get(f"/u/{username}/notes")
    assert notes_response.status_code == 200
    notes_page = notes_response.get_data(as_text=True)
    assert 'data-notes-filter-text' in notes_page
    assert 'data-notes-filter-status' in notes_page
    assert 'data-notes-filter-visibility' in notes_page
    assert 'data-note-card' in notes_page
    assert "Public Note" in notes_page
    assert "Private Note" not in notes_page
    assert "Draft Note" not in notes_page

    feed_response = client.get(f"/u/{username}/feed")
    assert feed_response.status_code == 200
    feed_page = feed_response.get_data(as_text=True)
    assert 'data-feed-filter-text' in feed_page
    assert 'data-feed-filter-category' in feed_page
    assert 'data-feed-card' in feed_page
    assert "Feed Subject" in feed_page
    assert "Hidden Feed Subject" not in feed_page


def test_drafts_route_shows_note_drafts_and_private_notes(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user(username="outsider")
        _user, owner = _create_local_user(username="owner")
        db.session.add_all(
            [
                NeeraNote(
                    profile_id=owner.id,
                    title="Public Published Note",
                    body="Should stay out of drafts.",
                    visibility="public",
                    status="published",
                ),
                NeeraNote(
                    profile_id=owner.id,
                    title="Private Published Note",
                    body="Drafts should include this.",
                    visibility="private",
                    status="published",
                ),
                NeeraNote(
                    profile_id=owner.id,
                    title="Draft Note",
                    body="Drafts should include this too.",
                    visibility="public",
                    status="draft",
                ),
            ]
        )
        db.session.commit()

    client = app.test_client()
    _login(client, username="outsider")
    forbidden_response = client.get("/u/owner/drafts")
    assert forbidden_response.status_code == 404

    client.post("/auth/logout")
    _login(client, username="owner")
    allowed_response = client.get("/u/owner/drafts")
    assert allowed_response.status_code == 200
    page = allowed_response.get_data(as_text=True)
    assert "Private Published Note" in page
    assert "Draft Note" in page
    assert "Public Published Note" not in page


def test_create_edit_delete_note_and_redirect_from_drafts(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user(username="owner")
        db.session.commit()

    client = app.test_client()
    _login(client, username="owner")

    create_response = client.post(
        "/me/notes",
        data={
            "title": "Fresh Note",
            "body": "First body",
            "visibility": "private",
            "status": "draft",
        },
        follow_redirects=True,
    )
    assert create_response.status_code == 200
    assert "Note draft saved." in create_response.get_data(as_text=True)

    with app.app_context():
        note = NeeraNote.query.filter_by(title="Fresh Note").first()
        assert note is not None
        note_id = note.id

    edit_response = client.post(
        f"/me/notes/{note_id}/edit",
        data={
            "title": "Fresh Note Updated",
            "body": "Published now",
            "visibility": "public",
            "status": "published",
            "return_tab": "Drafts",
        },
        follow_redirects=True,
    )
    assert edit_response.status_code == 200
    page = edit_response.get_data(as_text=True)
    assert "Note updated." in page
    assert "Drafts &amp; Private" in page or "Drafts & Private" in page

    delete_response = client.post(
        f"/me/notes/{note_id}/delete",
        data={"return_tab": "Notes"},
        follow_redirects=True,
    )
    assert delete_response.status_code == 200
    assert "Note deleted." in delete_response.get_data(as_text=True)

    with app.app_context():
        assert NeeraNote.query.get(note_id) is None


def test_bookmarks_route_requires_owner(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user(username="owner")
        _create_local_user(username="outsider")
        db.session.commit()

    client = app.test_client()
    _login(client, username="outsider")

    forbidden_response = client.get("/u/owner/bookmarks")
    assert forbidden_response.status_code == 404

    client.post("/auth/logout")
    _login(client, username="owner")
    allowed_response = client.get("/u/owner/bookmarks")
    assert allowed_response.status_code == 200
    assert "No bookmarks yet" in allowed_response.get_data(as_text=True)


def test_seed_catalog_cli_is_idempotent_and_item_pages_render(tmp_path):
    app = _build_test_app(tmp_path)
    runner = app.test_cli_runner()

    first_seed = runner.invoke(args=["seed-catalog"])
    assert first_seed.exit_code == 0
    assert "Seeded 20 new catalog items" in first_seed.output

    second_seed = runner.invoke(args=["seed-catalog"])
    assert second_seed.exit_code == 0
    assert "Seeded 0 new catalog items" in second_seed.output

    with app.app_context():
        assert NeeraItem.query.count() == 20
        assert NeeraItem.query.filter_by(category="book").count() == 5
        assert NeeraItem.query.filter_by(category="film").count() == 5
        assert NeeraItem.query.filter_by(category="song").count() == 5
        assert NeeraItem.query.filter_by(category="art").count() == 5
        first_item = NeeraItem.query.order_by(NeeraItem.id.asc()).first()
        item_id = first_item.id

    client = app.test_client()
    catalog_response = client.get("/items")
    assert catalog_response.status_code == 200
    assert "Work Catalog" in catalog_response.get_data(as_text=True)

    detail_response = client.get(f"/items/{item_id}")
    assert detail_response.status_code == 200
    assert first_item.title in detail_response.get_data(as_text=True)


def test_work_schema_supports_category_specific_metadata(tmp_path):
    app = _build_test_app(tmp_path)

    with app.app_context():
        book = NeeraItem(
            category="book",
            title="The Hobbit",
            creator_display_name="J.R.R. Tolkien",
            image_url="https://covers.openlibrary.org/b/isbn/9780547928227-L.jpg",
            description="Bilbo Baggins is drawn into an unexpected adventure.",
            source_type="openlibrary",
            source_id="9780547928227",
            is_user_submitted=False,
            metadata_confidence=1.0,
        )
        film = NeeraItem(
            category="film",
            title="Spirited Away",
            creator_display_name="Hayao Miyazaki",
            image_url="spirited-away-poster.jpg",
            description="A young girl enters a mysterious spirit world.",
            source_type="tmdb",
            source_id="129",
            is_user_submitted=False,
            metadata_confidence=1.0,
        )
        song = NeeraItem(
            category="song",
            title="Imagine",
            creator_display_name="John Lennon",
            image_url="imagine.jpg",
            description="A song envisioning a peaceful world.",
            source_type="musicbrainz",
            source_id="song-002",
            is_user_submitted=False,
            metadata_confidence=1.0,
        )
        art = NeeraItem(
            category="art",
            title="The Starry Night",
            creator_display_name="Vincent van Gogh",
            image_url="starry-night.jpg",
            description="A swirling depiction of the night sky.",
            source_type="metmuseum",
            source_id="art-001",
            is_user_submitted=False,
            metadata_confidence=1.0,
        )
        db.session.add_all([book, film, song, art])
        db.session.flush()
        db.session.add_all(
            [
                NeeraBookMetadata(
                    work_id=book.id,
                    author="J.R.R. Tolkien",
                    year=1937,
                    pages=310,
                    publisher="George Allen & Unwin",
                    isbn="9780547928227",
                    language="English",
                ),
                NeeraFilmMetadata(
                    work_id=film.id,
                    director="Hayao Miyazaki",
                    year=2001,
                    runtime_minutes=125,
                    country="Japan",
                    language="Japanese",
                ),
                NeeraSongMetadata(
                    work_id=song.id,
                    artist="John Lennon",
                    album="Imagine",
                    year=1971,
                    duration_seconds=183,
                ),
                NeeraArtMetadata(
                    work_id=art.id,
                    artist="Vincent van Gogh",
                    year=1889,
                    medium="Oil on Canvas",
                    movement="Post-Impressionism",
                    museum="Museum of Modern Art",
                ),
            ]
        )
        db.session.commit()

        stored_book = NeeraItem.query.filter_by(title="The Hobbit").first()
        stored_film = NeeraItem.query.filter_by(title="Spirited Away").first()
        stored_song = NeeraItem.query.filter_by(title="Imagine").first()
        stored_art = NeeraItem.query.filter_by(title="The Starry Night").first()

        assert stored_book.book_metadata.author == "J.R.R. Tolkien"
        assert stored_book.year_value == 1937
        assert stored_book.length_label == "310 pages"
        assert stored_film.film_metadata.runtime_minutes == 125
        assert stored_film.length_label == "125 min"
        assert stored_song.song_metadata.duration_seconds == 183
        assert stored_song.length_label == "3m 03s"
        assert stored_art.art_metadata.medium == "Oil on Canvas"
        assert stored_art.length_label == "Oil on Canvas"


def test_item_pages_render_with_new_work_schema(tmp_path):
    app = _build_test_app(tmp_path)

    with app.app_context():
        item = NeeraItem(
            category="book",
            title="The Hobbit",
            creator_display_name="J.R.R. Tolkien",
            image_url="https://covers.openlibrary.org/b/isbn/9780547928227-L.jpg",
            description="Bilbo Baggins is drawn into an unexpected adventure.",
            source_type="openlibrary",
            source_id="9780547928227",
            is_user_submitted=False,
            metadata_confidence=1.0,
        )
        db.session.add(item)
        db.session.flush()
        db.session.add(
            NeeraBookMetadata(
                work_id=item.id,
                author="J.R.R. Tolkien",
                year=1937,
                pages=310,
                publisher="George Allen & Unwin",
                isbn="9780547928227",
                language="English",
            )
        )
        db.session.add(
            Review(
                profile_id=_create_local_user(username="reviewer")[1].id,
                category="books",
                subject="The Hobbit",
                body="Still wildly inviting.",
                rating=5,
            )
        )
        db.session.commit()
        item_id = item.id

    client = app.test_client()
    catalog_response = client.get("/items")
    assert catalog_response.status_code == 200
    catalog_page = catalog_response.get_data(as_text=True)
    assert "The Hobbit" in catalog_page
    assert "J.R.R. Tolkien" in catalog_page
    assert "310 pages" in catalog_page

    detail_response = client.get(f"/items/{item_id}")
    assert detail_response.status_code == 200
    detail_page = detail_response.get_data(as_text=True)
    assert "The Hobbit" in detail_page
    assert "Author:" in detail_page
    assert "J.R.R. Tolkien" in detail_page
    assert "ISBN:" in detail_page
    assert "9780547928227" in detail_page
    assert "Still wildly inviting." in detail_page


def test_create_work_submission_persists_new_entry(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user()
        db.session.commit()

    client = app.test_client()
    _login(client)

    response = client.post(
        "/items",
        data={
            "category": "book",
            "title": "A Wizard of Earthsea",
            "creator_display_name": "Ursula K. Le Guin",
            "image_url": "https://covers.example/earthsea.jpg",
            "description": "A young wizard confronts the shadow he has unleashed.",
            "book_author": "Ursula K. Le Guin",
            "book_year": "1968",
            "book_pages": "205",
            "book_publisher": "Parnassus Press",
            "book_isbn": "9780547773742",
            "book_language": "English",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Work submitted." in page
    assert "A Wizard of Earthsea" in page
    assert "ISBN:" in page
    assert "9780547773742" in page

    with app.app_context():
        created = NeeraItem.query.filter_by(title="A Wizard of Earthsea").first()
        assert created is not None
        assert created.is_user_submitted is True
        assert created.source_type == "user"
        assert created.book_metadata is not None
        assert created.book_metadata.pages == 205
        assert created.metadata_confidence == 1.0


def test_create_work_form_renders_category_aware_metadata_groups(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user()
        db.session.commit()

    client = app.test_client()
    _login(client)

    response = client.get("/items")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'data-work-form' in page
    assert 'data-category-select' in page
    assert 'data-metadata-group="book"' in page
    assert 'data-metadata-group="film" hidden' in page
    assert 'data-metadata-group="song" hidden' in page
    assert 'data-metadata-group="art" hidden' in page
    assert 'categorySelect.addEventListener("change", syncGroups);' in page


def test_create_work_submission_accepts_uploaded_image(tmp_path):
    app = _build_test_app(tmp_path)
    with app.app_context():
        _create_local_user()
        db.session.commit()

    client = app.test_client()
    _login(client)

    response = client.post(
        "/items",
        data={
            "category": "song",
            "title": "New Song",
            "creator_display_name": "New Artist",
            "description": "Uploaded art test.",
            "song_artist": "New Artist",
            "song_album": "Debut",
            "song_year": "2024",
            "song_duration_seconds": "201",
            "image_file": (BytesIO(b"fake-image-bytes"), "cover.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Work submitted." in response.get_data(as_text=True)

    with app.app_context():
        created = NeeraItem.query.filter_by(title="New Song").first()
        assert created is not None
        assert created.image_url.startswith("/uploads/works/")

    upload_response = client.get(created.image_url)
    assert upload_response.status_code == 200
    assert upload_response.data == b"fake-image-bytes"
