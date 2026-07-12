from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models import Base, PostSource, PostStatus


def test_final_v1_tables_are_registered():
    assert set(Base.metadata.tables) == {
        "account_tokens",
        "users",
        "user_profiles",
        "content_bank",
        "posts",
        "user_workspaces",
        "workspace_profiles",
        "workspace_memories",
        "workspace_posts",
        "workspace_messages",
        "workspace_metadata",
    }


def test_model_metadata_compiles_for_postgresql():
    dialect = postgresql.dialect()

    for table in Base.metadata.sorted_tables:
        sql = str(CreateTable(table).compile(dialect=dialect))
        assert f"CREATE TABLE {table.name}" in sql


def test_post_workflow_values_match_product_contract():
    assert {status.value for status in PostStatus} == {
        "draft",
        "approved",
        "scheduled",
        "published",
        "skipped",
    }
    assert {source.value for source in PostSource} == {
        "user_initiated",
        "mira_initiated",
    }
