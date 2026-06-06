import click

from .catalog_seed import CATALOG_SEED_DATA

from .extensions import db
from .models import NeeraList, NeeraListItem, LocalCredential, Review, UserProfile
from .works import seed_catalog_items


def _seed_profile_content(profile):
    if NeeraList.query.filter_by(profile_id=profile.id).count() == 0:
        starter_lists = [
            NeeraList(
                profile_id=profile.id,
                category="books",
                title="Summer Reads",
                description="Beach days, slow nights, and unforgettable stories.",
                item_count=3,
            ),
            NeeraList(
                profile_id=profile.id,
                category="songs",
                title="Songs that Heal",
                description="For the days when you need a little extra softness.",
                item_count=3,
            ),
            NeeraList(
                profile_id=profile.id,
                category="films",
                title="10 Films You Must Watch",
                description="Timeless films. Unmissable.",
                item_count=3,
            ),
        ]
        db.session.add_all(starter_lists)
        db.session.flush()

        db.session.add_all(
            [
                NeeraListItem(list_id=starter_lists[0].id, position=1, title="The Left Hand of Darkness", creator_name="Ursula K. Le Guin"),
                NeeraListItem(list_id=starter_lists[0].id, position=2, title="Never Let Me Go", creator_name="Kazuo Ishiguro"),
                NeeraListItem(list_id=starter_lists[0].id, position=3, title="A Visit from the Goon Squad", creator_name="Jennifer Egan"),
                NeeraListItem(list_id=starter_lists[1].id, position=1, title="Nights", creator_name="Frank Ocean"),
                NeeraListItem(list_id=starter_lists[1].id, position=2, title="Simulation Swarm", creator_name="Big Thief"),
                NeeraListItem(list_id=starter_lists[1].id, position=3, title="Kintsugi", creator_name="Lana Del Rey"),
                NeeraListItem(list_id=starter_lists[2].id, position=1, title="Past Lives", creator_name="Celine Song"),
                NeeraListItem(list_id=starter_lists[2].id, position=2, title="Portrait of a Lady on Fire", creator_name="Celine Sciamma"),
                NeeraListItem(list_id=starter_lists[2].id, position=3, title="In the Mood for Love", creator_name="Wong Kar-wai"),
            ]
        )


def _seed_catalog_items():
    return seed_catalog_items(db.session)

    if Review.query.filter_by(profile_id=profile.id).count() == 0:
        db.session.add_all(
            [
                Review(
                    profile_id=profile.id,
                    category="books",
                    subject="The Left Hand of Darkness",
                    body="A deeply human sci-fi novel that still feels modern.",
                    rating=5,
                ),
                Review(
                    profile_id=profile.id,
                    category="songs",
                    subject="Nights by Frank Ocean",
                    body="The structural switch in the middle still feels magical.",
                    rating=5,
                ),
                Review(
                    profile_id=profile.id,
                    category="films",
                    subject="Past Lives",
                    body="Quiet, precise, and emotionally devastating in the best way.",
                    rating=4,
                ),
            ]
        )


def register_cli(app):
    @app.cli.command("seed-catalog")
    def seed_catalog():
        created_count = _seed_catalog_items()
        db.session.commit()
        click.echo(f"Seeded {created_count} new catalog items")

    @app.cli.command("setup")
    @click.option("--username", default="testuser", show_default=True)
    @click.option("--password", default="test123", show_default=True)
    def setup(username, password):
        user = LocalCredential.query.filter_by(username=username).first()
        if user is None:
            user = LocalCredential(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            profile = user.ensure_profile()
            db.session.flush()
            _seed_profile_content(profile)
            db.session.commit()
            click.echo(f"Created local user '{username}'")
        else:
            profile = user.ensure_profile()
            db.session.flush()
            _seed_profile_content(profile)
            db.session.commit()
            click.echo(f"User '{username}' already exists")

        demo_profile = UserProfile.query.filter_by(user_id="demo").first()
        if demo_profile is None:
            demo_profile = UserProfile(
                user_id="demo",
                username="neera",
                display_name="Neera",
                bio="Curating pieces of art that feel like home.",
                is_public=True,
            )
            db.session.add(demo_profile)
            db.session.flush()
            _seed_profile_content(demo_profile)
            db.session.commit()
            click.echo("Created demo profile with starter lists and reviews")

        created_count = _seed_catalog_items()
        db.session.commit()
        click.echo(f"Catalog ready ({created_count} new items added, {len(CATALOG_SEED_DATA)} prepared records total)")

        click.echo("Setup complete")
