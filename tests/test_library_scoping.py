"""Library/workspace scoping: proves queries never cross the library boundary."""

import uuid
from unittest.mock import MagicMock, patch

import numpy as np

from stepwise.indexing.indexer import TEXT_EMB_DIM

# ── Fake Chroma that honours the where-clause the retriever builds ──────────────

def _match(meta: dict, where) -> bool:
    """Evaluate the subset of Chroma's where-syntax the retriever emits."""
    if not where:
        return True
    if "$and" in where:
        return all(_match(meta, clause) for clause in where["$and"])
    for field, cond in where.items():
        if "$eq" in cond and meta.get(field) != cond["$eq"]:
            return False
        if "$in" in cond and meta.get(field) not in cond["$in"]:
            return False
    return True


class FakeCollection:
    def __init__(self, records=None):
        # records: list of {id, document, metadata}
        self._records = records or []

    def count(self):
        return len(self._records)

    def query(self, query_embeddings, n_results, where=None, include=None):
        matched = [r for r in self._records if _match(r["metadata"], where)][:n_results]
        return {
            "ids": [[r["id"] for r in matched]],
            "documents": [[r["document"] for r in matched]],
            "metadatas": [[r["metadata"] for r in matched]],
            "distances": [[0.5 for _ in matched]],
        }


class FakeChroma:
    def __init__(self, collections):
        self._collections = collections

    def get_or_create_collection(self, name):
        return self._collections[name]


def _step_record(step_id, library_id, tutorial_id, n):
    return {
        "id": step_id,
        "document": f"Step {n}. Do thing {n} in {library_id}.",
        "metadata": {
            "library_id": library_id,
            "tutorial_id": tutorial_id,
            "step_number": n,
            "step_id": step_id,
            "timestamp_start": 0,
            "visual_reference": "",
        },
    }


def _two_library_chroma():
    steps = FakeCollection([
        _step_record("sA1", "libA", "tutA", 1),
        _step_record("sA2", "libA", "tutA", 2),
        _step_record("sB1", "libB", "tutB", 1),
        _step_record("sB2", "libB", "tutB", 2),
    ])
    # Empty centroids → pre-filter returns None → search whole library.
    return FakeChroma({"steps": steps, "tutorial_centroids": FakeCollection([])})


class TestCrossLibraryIsolation:
    def _lookup(self, library_id):
        from stepwise.retrieval import retriever

        text_model = MagicMock()
        text_model.encode.return_value = np.ones(TEXT_EMB_DIM, dtype=np.float32)
        cross_encoder = MagicMock()
        cross_encoder.predict.side_effect = lambda pairs: np.ones(len(pairs))

        with (
            patch.object(retriever, "_hypothetical_step", return_value="hypo."),
            patch.object(retriever, "_get_text_model", return_value=text_model),
            patch.object(retriever, "_get_cross_encoder", return_value=cross_encoder),
            patch.object(retriever, "_get_chroma", return_value=_two_library_chroma()),
        ):
            return retriever._chromadb_lookup("how?", library_id, None, 5, [])

    def test_query_returns_only_its_library(self):
        _docs, metas_a, _dists, _timing = self._lookup("libA")
        assert metas_a, "expected results in libA"
        assert {m["library_id"] for m in metas_a} == {"libA"}
        assert {m["step_id"] for m in metas_a} <= {"sA1", "sA2"}

        _docs, metas_b, _dists, _timing = self._lookup("libB")
        assert {m["library_id"] for m in metas_b} == {"libB"}
        assert {m["step_id"] for m in metas_b} <= {"sB1", "sB2"}


class TestIndexMetadataCarriesLibrary:
    def test_step_and_centroid_metadata_include_library_id(self):
        from stepwise.indexing import indexer
        from stepwise.models import Step, Tutorial

        tutorial = Tutorial(
            id="tutA",
            library_id="libA",
            source_url="https://example.com/a",
            title="A",
            steps=[
                Step(id="s1", tutorial_id="tutA", library_id="libA",
                     step_number=1, title="One", description="Do one."),
                Step(id="s2", tutorial_id="tutA", library_id="libA",
                     step_number=2, title="Two", description="Do two."),
            ],
        )

        steps_col, centroids_col = MagicMock(), MagicMock()
        chroma = FakeChroma({"steps": steps_col, "tutorial_centroids": centroids_col})
        text_model = MagicMock()
        text_model.encode.return_value = np.ones((2, TEXT_EMB_DIM), dtype=np.float32)

        with (
            patch.object(indexer, "_get_chroma", return_value=chroma),
            patch.object(indexer, "_get_text_model", return_value=text_model),
            patch.object(indexer, "_get_clip_model", return_value=MagicMock()),
        ):
            indexer._index_vectors(tutorial)

        step_metas = steps_col.upsert.call_args.kwargs["metadatas"]
        assert all(m["library_id"] == "libA" for m in step_metas)
        centroid_metas = centroids_col.upsert.call_args.kwargs["metadatas"]
        assert centroid_metas[0]["library_id"] == "libA"


class TestQueryLogScoped:
    def test_query_log_written_with_library_id(self):
        from stepwise.indexing.indexer import get_db_session
        from stepwise.models import QueryLogDB
        from stepwise.retrieval import retriever

        lib = f"lib-{uuid.uuid4().hex[:8]}"
        # Empty retrieval → early return after writing the log (no LLM call needed).
        empty = FakeChroma({"steps": FakeCollection([]),
                            "tutorial_centroids": FakeCollection([])})
        text_model = MagicMock()
        text_model.encode.return_value = np.ones(TEXT_EMB_DIM, dtype=np.float32)

        with (
            patch.object(retriever, "_hypothetical_step", return_value="hypo."),
            patch.object(retriever, "_get_text_model", return_value=text_model),
            patch.object(retriever, "_get_chroma", return_value=empty),
        ):
            result = retriever.query_steps("anything", library_id=lib)

        assert result["steps"] == []
        with get_db_session() as session:
            row = session.query(QueryLogDB).filter_by(library_id=lib).first()
        assert row is not None
        assert row.library_id == lib


class TestLibraryApi:
    def test_create_and_list_libraries(self, app_client):
        resp = app_client.post("/libraries", json={"name": "Stripe"})
        assert resp.status_code == 201
        created = resp.json()
        assert created["name"] == "Stripe"

        listed = app_client.get("/libraries").json()
        ids = {lib["id"] for lib in listed}
        assert "local" in ids            # default library always present
        assert created["id"] in ids

    def test_tutorials_filtered_by_library(self, app_client):
        from stepwise.indexing.indexer import get_db_session
        from stepwise.models import TutorialDB

        lib_a, lib_b = f"a-{uuid.uuid4().hex[:6]}", f"b-{uuid.uuid4().hex[:6]}"
        with get_db_session() as session:
            session.add(TutorialDB(id=f"t-{lib_a}", library_id=lib_a,
                                   source_url=f"u://{lib_a}", title="A"))
            session.add(TutorialDB(id=f"t-{lib_b}", library_id=lib_b,
                                   source_url=f"u://{lib_b}", title="B"))
            session.commit()

        got = app_client.get(f"/tutorials?library_id={lib_a}").json()
        ids = {t["id"] for t in got}
        assert f"t-{lib_a}" in ids
        assert f"t-{lib_b}" not in ids
