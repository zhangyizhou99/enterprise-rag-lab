"""Budgeted same-section context expansion for ranked retrieval anchors."""

from __future__ import annotations

from typing import Protocol, Sequence

from enterprise_rag_lab.models import (
    Chunk,
    ContextExpansionResult,
    ExpandedChunk,
    HybridSearchResult,
)

CONTEXT_EXPANDER_VERSION = "0.2.0"
DEFAULT_NEIGHBOR_DEPTH = 1
DEFAULT_MAX_CONTEXT_CHARACTERS = 2400


class LatestChunkStore(Protocol):
    def get_latest_chunks(
        self,
        document_id: str,
    ) -> tuple[str, tuple[Chunk, ...]] | None: ...


class HybridRetriever(Protocol):
    @property
    def retriever_id(self) -> str: ...

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> Sequence[HybridSearchResult]: ...


class ContextExpansionService:
    def __init__(
        self,
        store: LatestChunkStore,
        retriever: HybridRetriever,
        neighbor_depth: int = DEFAULT_NEIGHBOR_DEPTH,
        max_context_characters: int = DEFAULT_MAX_CONTEXT_CHARACTERS,
    ) -> None:
        if neighbor_depth < 1 or neighbor_depth > 3:
            raise ValueError("Neighbor depth must be between 1 and 3")
        if max_context_characters < 1:
            raise ValueError("Maximum context characters must be positive")
        self.store = store
        self.retriever = retriever
        self.neighbor_depth = neighbor_depth
        self.max_context_characters = max_context_characters

    @property
    def retriever_id(self) -> str:
        return (
            f"{self.retriever.retriever_id}_context_section_"
            f"d{self.neighbor_depth}_b{self.max_context_characters}_"
            f"v{CONTEXT_EXPANDER_VERSION}"
        )

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> tuple[ContextExpansionResult, ...]:
        anchors = tuple(self.retriever.search(query, limit))
        excluded_ids = {anchor.chunk_id for anchor in anchors}
        documents: dict[str, dict[str, Chunk]] = {}
        return tuple(
            self._expand(anchor, excluded_ids, documents) for anchor in anchors
        )

    def _expand(
        self,
        anchor: HybridSearchResult,
        excluded_ids: set[str],
        documents: dict[str, dict[str, Chunk]],
    ) -> ContextExpansionResult:
        chunks_by_id = documents.get(anchor.document_id)
        if chunks_by_id is None:
            source = self.store.get_latest_chunks(anchor.document_id)
            if source is None:
                raise RuntimeError(
                    f"No current chunks are available for {anchor.document_id}"
                )
            chunks_by_id = {chunk.chunk_id: chunk for chunk in source[1]}
            documents[anchor.document_id] = chunks_by_id

        anchor_chunk = chunks_by_id.get(anchor.chunk_id)
        if anchor_chunk is None:
            raise RuntimeError(f"Anchor {anchor.chunk_id} is not a current chunk")
        if anchor_chunk.text != anchor.text:
            raise RuntimeError(f"Anchor {anchor.chunk_id} text is stale")

        candidates = self._neighbor_candidates(anchor_chunk, chunks_by_id)
        selected: list[tuple[str, int, Chunk]] = []
        context_characters = len(anchor_chunk.text)
        for relation, distance, chunk in candidates:
            if chunk.chunk_id in excluded_ids:
                continue
            projected = context_characters + 2 + len(chunk.text)
            if projected > self.max_context_characters:
                continue
            selected.append((relation, distance, chunk))
            excluded_ids.add(chunk.chunk_id)
            context_characters = projected

        selected.sort(key=lambda item: item[2].ordinal)
        context_chunks = [anchor_chunk, *(item[2] for item in selected)]
        context_chunks.sort(key=lambda chunk: chunk.ordinal)
        context_text = "\n\n".join(chunk.text for chunk in context_chunks)
        return ContextExpansionResult(
            anchor=anchor,
            expanded_chunks=tuple(
                ExpandedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    heading_path=chunk.heading_path,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    source_ordinals=chunk.source_ordinals,
                    relation=relation,
                    distance=distance,
                )
                for relation, distance, chunk in selected
            ),
            context_text=context_text,
            context_character_count=len(context_text),
            max_context_characters=self.max_context_characters,
            context_budget_exceeded=(
                len(anchor_chunk.text) > self.max_context_characters
            ),
        )

    def _neighbor_candidates(
        self,
        anchor: Chunk,
        chunks_by_id: dict[str, Chunk],
    ) -> tuple[tuple[str, int, Chunk], ...]:
        candidates: list[tuple[str, int, Chunk]] = []
        previous_id = anchor.previous_chunk_id
        next_id = anchor.next_chunk_id
        for distance in range(1, self.neighbor_depth + 1):
            previous = self._neighbor(previous_id, anchor, chunks_by_id)
            if previous is not None:
                candidates.append(("previous", distance, previous))
                previous_id = previous.previous_chunk_id
            else:
                previous_id = None

            following = self._neighbor(next_id, anchor, chunks_by_id)
            if following is not None:
                candidates.append(("next", distance, following))
                next_id = following.next_chunk_id
            else:
                next_id = None
        return tuple(candidates)

    @staticmethod
    def _neighbor(
        chunk_id: str | None,
        anchor: Chunk,
        chunks_by_id: dict[str, Chunk],
    ) -> Chunk | None:
        if chunk_id is None:
            return None
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            raise RuntimeError(
                f"Neighbor {chunk_id} referenced by {anchor.chunk_id} is not current"
            )
        if chunk.document_id != anchor.document_id:
            raise RuntimeError(f"Neighbor {chunk_id} crosses a document boundary")
        return chunk if _same_section_family(anchor, chunk) else None


def _same_section_family(anchor: Chunk, neighbor: Chunk) -> bool:
    anchor_pages = (anchor.page_start, anchor.page_end)
    neighbor_pages = (neighbor.page_start, neighbor.page_end)
    if any(value is not None for value in (*anchor_pages, *neighbor_pages)):
        if anchor_pages != neighbor_pages:
            return False

    anchor_path = anchor.heading_path
    neighbor_path = neighbor.heading_path
    if anchor_path == neighbor_path:
        return True
    shorter, longer = sorted((anchor_path, neighbor_path), key=len)
    if shorter and longer[: len(shorter)] == shorter:
        return True
    return (
        len(anchor_path) > 1
        and len(neighbor_path) > 1
        and anchor_path[:-1] == neighbor_path[:-1]
    )