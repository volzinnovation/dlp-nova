"""Publish a matched OSM map, spatial index and completed ontology revision.

The host owns publications as immutable snapshots. Updating the map builds a
candidate source/index and ontology closure before swapping the published pair.
Old publications stay usable until their owner closes them. Query evaluation is
read-only; it does not recompile the static ontology for each query.
"""
from dataclasses import dataclass, field
import threading

from .model import IncompleteReasoningError, InconsistentOntologyError
from .osm import OSMError, OSMStore
from .query_runtime import QueryScope
from .reasoner import Reasoner, copy_graph


@dataclass(frozen=True)
class MapPublication:
    map: object
    reasoner: Reasoner
    _token: object = field(repr=False)

    def validate(self):
        """Reject a caller-mutated ontology or explicitly closed spatial index."""
        if self.reasoner._query_cache_token() != self._token:
            raise OSMError("STALE_SOURCE", "Published ontology was mutated; use a new publication")
        self.reasoner._guard()
        self.map.point_index._check()
        return self

    @property
    def scope(self):
        self.validate()
        return QueryScope("urn:dlp:osm-publication", self.map.digest)

    def close(self):
        self.map.point_index.close()


class MapRuntime:
    """Serialized source updates with atomic ontology/map publication.

    ``ontology`` includes the stable schema and any separately managed facts
    such as sign observations. This first adapter rebuilds the candidate closure
    on a map transaction; it never mutates a published Reasoner in place.
    ``snapshot`` always refers to the last complete, consistent publication.
    A failed update sets ``complete=False`` while preserving that old revision.
    """
    def __init__(self, ontology, *, profile="L0", backend="python", limits=None,
                 pbf_reader=None, reasoner_options=None):
        self._ontology = copy_graph(ontology)
        self.profile, self.backend = profile, backend
        self.limits, self.pbf_reader = limits, pbf_reader
        self.reasoner_options = dict(reasoner_options or {})
        if {"profile", "backend"} & self.reasoner_options.keys():
            raise ValueError("Pass profile/backend directly, not in reasoner_options")
        self.snapshot, self.complete = None, False
        self._lock = threading.Lock()
        self._closed = False

    def _transaction(self, operation, *args, **kwargs):
        if self._closed:
            raise OSMError("CLOSED", "Map runtime is closed")
        if not self._lock.acquire(blocking=False):
            raise OSMError("REENTRANT", "Map publication transaction is already running")
        previous = self.snapshot
        candidate = None
        try:
            if self._closed:
                raise OSMError("CLOSED", "Map runtime is closed")
            if previous is not None:
                previous.validate()
            store = OSMStore(limits=self.limits, backend=self.backend, pbf_reader=self.pbf_reader)
            store.snapshot = None if previous is None else previous.map
            candidate = getattr(store, operation)(*args, **kwargs)
            if previous is not None and candidate is previous.map:
                self.complete = True
                return previous
            graph = copy_graph(self._ontology)
            for triple in candidate.triples:
                graph.add(triple)
            reasoner = Reasoner(graph, profile=self.profile, backend=self.backend,
                                **self.reasoner_options)
            if not reasoner.complete:
                raise IncompleteReasoningError("Candidate map ontology did not complete")
            if reasoner.consistency == "inconsistent":
                raise InconsistentOntologyError("Candidate map ontology is inconsistent")
            publication = MapPublication(candidate, reasoner, reasoner._query_cache_token())
            publication.validate()
            self.snapshot, self.complete = publication, True
            return publication
        except BaseException:
            self.complete = False
            if candidate is not None and (previous is None or candidate is not previous.map):
                candidate.point_index.close()
            raise
        finally:
            self._lock.release()

    def load_snapshot(self, records, *, source):
        return self._transaction("load_snapshot", records, source=source)

    def load_xml(self, source, *, source_id):
        return self._transaction("load_xml", source, source_id=source_id)

    def load_pbf(self, path, *, source_id):
        return self._transaction("load_pbf", path, source_id=source_id)

    def apply_changes(self, changes):
        return self._transaction("apply_changes", changes)

    def apply_xml(self, source):
        return self._transaction("apply_xml", source)

    def close(self):
        if not self._lock.acquire(blocking=False):
            raise OSMError("REENTRANT", "Cannot close during a map publication transaction")
        try:
            if self.snapshot is not None:
                self.snapshot.close()
            self._closed = True
        finally:
            self._lock.release()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
