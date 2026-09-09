#include "native_store.h"

#include <algorithm>
#include <cstdio>
#include <limits>
#include <memory>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace {
using Id = uint64_t;
using Row = std::vector<Id>;

thread_local char last_error[1024] = {};

template <typename Operation> int guarded(Operation operation) noexcept {
    last_error[0] = '\0';
    try {
        operation();
        return 0;
    } catch (const std::exception &error) {
        std::snprintf(last_error, sizeof(last_error), "%s", error.what());
    } catch (...) {
        std::snprintf(last_error, sizeof(last_error), "unknown native backend error");
    }
    return -1;
}

void require(bool condition, const char *message) {
    if (!condition) throw std::invalid_argument(message);
}

size_t cells(size_t rows, size_t arity) {
    require(arity == 0 || rows <= std::numeric_limits<size_t>::max() / arity,
            "row buffer dimensions overflow");
    const size_t count = rows * arity;
    require(count <= std::numeric_limits<size_t>::max() / sizeof(Id),
            "row buffer byte size overflows");
    return count;
}

struct RowHash {
    size_t operator()(const Row &row) const noexcept {
        // Mix every term and position, including the arity of the empty tuple.
        uint64_t hash = 0x9e3779b97f4a7c15ULL ^ row.size();
        for (uint64_t value : row) {
            value ^= value >> 30;
            value *= 0xbf58476d1ce4e5b9ULL;
            value ^= value >> 27;
            value *= 0x94d049bb133111ebULL;
            value ^= value >> 31;
            hash ^= value + 0x9e3779b97f4a7c15ULL + (hash << 6) + (hash >> 2);
        }
        return static_cast<size_t>(hash);
    }
};

using Bucket = std::unordered_set<const Row *>;

struct Selection {
    const Bucket *bucket = nullptr;
    const Row *singleton = nullptr;

    size_t size() const { return singleton ? 1 : bucket ? bucket->size() : 0; }
};

struct Relation {
    explicit Relation(size_t arity) : arity(arity), columns(arity) {}

    size_t arity;
    std::unordered_set<Row, RowHash> rows;
    Bucket all;
    std::vector<std::unordered_map<Id, Bucket>> columns;

    bool contains(const Row &row) const { return rows.find(row) != rows.end(); }

    void add(Row row) {
        auto inserted = rows.emplace(std::move(row));
        if (!inserted.second) return;
        const Row *stored = &*inserted.first;
        try {
            all.insert(stored);
            for (size_t column = 0; column < arity; ++column)
                columns[column][(*stored)[column]].insert(stored);
        } catch (...) {
            // Keep membership and every index consistent after allocation
            // failure, including a newly-created but still empty bucket.
            remove_indexes(stored);
            rows.erase(inserted.first);
            throw;
        }
    }

    void remove_indexes(const Row *row) noexcept {
        all.erase(row);
        for (size_t column = 0; column < arity; ++column) {
            auto found = columns[column].find((*row)[column]);
            if (found == columns[column].end()) continue;
            found->second.erase(row);
            if (found->second.empty()) columns[column].erase(found);
        }
    }

    void discard(const Row &row) {
        const auto found = rows.find(row);
        if (found == rows.end()) return;
        remove_indexes(&*found);
        rows.erase(found);
    }

    Selection lookup(const Row &values) const {
        if (std::find(values.begin(), values.end(), Id{0}) == values.end()) {
            const auto found = rows.find(values);
            return {nullptr, found == rows.end() ? nullptr : &*found};
        }
        const Bucket *best = &all;
        for (size_t column = 0; column < arity; ++column) {
            if (values[column] == 0) continue;
            const auto found = columns[column].find(values[column]);
            if (found == columns[column].end()) return {};
            if (found->second.size() < best->size()) best = &found->second;
        }
        return {best, nullptr};
    }
};

struct Store {
    std::unordered_map<Id, std::unique_ptr<Relation>> relations;
    uint64_t generation = 0;

    void mutate() {
        require(generation != std::numeric_limits<uint64_t>::max(),
                "native store generation exhausted");
        ++generation;
    }

    const Relation *find(Id predicate, size_t arity) const {
        auto found = relations.find(predicate);
        if (found == relations.end()) return nullptr;
        require(found->second->arity == arity, "predicate arity mismatch");
        return found->second.get();
    }
};

// Bulk operations may fail after applying a prefix. Even on that path, a
// predicate with no tuples must not retain stale arity metadata.
struct PruneEmptyRelation {
    Store &store;
    Id predicate;
    Relation &relation;
    ~PruneEmptyRelation() {
        if (relation.rows.empty()) store.relations.erase(predicate);
    }
};

void validate_rows(Id predicate, size_t arity, const Id *data, size_t row_count) {
    require(predicate != 0, "predicate ID 0 is reserved");
    const size_t count = cells(row_count, arity);
    require(count == 0 || data != nullptr, "row data is null");
    for (size_t i = 0; i < count; ++i)
        require(data[i] != 0, "term ID 0 is reserved");
}

Row copy_row(const Id *data, size_t arity) {
    // Avoid pointer arithmetic on nullptr for zero-arity tuples.
    return arity ? Row(data, data + arity) : Row{};
}

struct Atom {
    Id predicate;
    std::vector<int32_t> slots;
    Row constants;
    Store *store;
};

struct Frame {
    size_t atom;
    std::vector<size_t> remaining;
    Row binding;
    Selection selection;
    Bucket::const_iterator next;
    bool singleton_consumed = false;

    const Row *take() {
        if (selection.singleton) {
            if (singleton_consumed) return nullptr;
            singleton_consumed = true;
            return selection.singleton;
        }
        if (next == selection.bucket->end()) return nullptr;
        return *next++;
    }
};

struct Query {
    std::shared_ptr<Store> store;
    std::shared_ptr<Store> delta;
    uint64_t store_generation = 0;
    uint64_t delta_generation = 0;
    size_t slot_count;
    std::vector<Atom> atoms;
    Row initial;
    std::vector<Frame> stack;
    uint64_t candidates = 0;
    uint64_t matches = 0;
    bool started = false;
    bool done = false;
    bool failed = false;

    bool push_frame(const std::vector<size_t> &remaining, Row binding) {
        Selection best;
        size_t chosen = 0;
        size_t size = std::numeric_limits<size_t>::max();
        for (size_t position : remaining) {
            const Atom &atom = atoms[position];
            const Relation *relation = atom.store->find(atom.predicate, atom.slots.size());
            if (!relation) return false;
            Row values(atom.slots.size());
            for (size_t i = 0; i < values.size(); ++i)
                values[i] = atom.slots[i] < 0 ? atom.constants[i] : binding[atom.slots[i]];
            Selection selected = relation->lookup(values);
            const size_t count = selected.size();
            if (!count) return false;
            if (count < size) {
                best = selected;
                chosen = position;
                size = count;
            }
        }
        Frame frame;
        frame.atom = chosen;
        frame.binding = std::move(binding);
        frame.selection = best;
        if (best.bucket) frame.next = best.bucket->begin();
        frame.remaining.reserve(remaining.size() - 1);
        for (size_t position : remaining)
            if (position != chosen) frame.remaining.push_back(position);
        stack.push_back(std::move(frame));
        return true;
    }

    bool advance(Id *output) {
        if (done) return false;
        if (!started) {
            started = true;
            if (atoms.empty()) {
                if (slot_count) std::copy(initial.begin(), initial.end(), output);
                ++matches;
                done = true;
                return true;
            }
            std::vector<size_t> remaining(atoms.size());
            for (size_t i = 0; i < atoms.size(); ++i) remaining[i] = i;
            push_frame(remaining, initial);
        }
        while (!stack.empty()) {
            Frame &frame = stack.back();
            const Row *row = frame.take();
            if (!row) {
                stack.pop_back();
                continue;
            }
            ++candidates;
            const Atom &atom = atoms[frame.atom];
            Row extended = frame.binding;
            bool accepted = true;
            for (size_t i = 0; i < atom.slots.size(); ++i) {
                const int32_t slot = atom.slots[i];
                const Id actual = (*row)[i];
                if (slot < 0) {
                    if (atom.constants[i] != actual) { accepted = false; break; }
                } else if (extended[slot] && extended[slot] != actual) {
                    accepted = false;
                    break;
                } else {
                    extended[slot] = actual;
                }
            }
            if (!accepted) continue;
            if (frame.remaining.empty()) {
                if (slot_count) std::copy(extended.begin(), extended.end(), output);
                ++matches;
                return true;
            }
            // push_frame consumes remaining before stack growth can invalidate
            // this frame reference; all plan data and stores remain owned.
            push_frame(frame.remaining, std::move(extended));
        }
        done = true;
        return false;
    }
};
} // namespace

struct dlp_store { std::shared_ptr<Store> value; };
struct dlp_query { Query value; };

extern "C" {
uint32_t dlp_abi_version(void) { return 1; }
const char *dlp_last_error(void) { return last_error; }

int dlp_store_new(dlp_store **out) {
    if (out) *out = nullptr;
    return guarded([&] {
        require(out != nullptr, "store output is null");
        auto handle = std::make_unique<dlp_store>();
        handle->value = std::make_shared<Store>();
        *out = handle.release();
    });
}

void dlp_store_free(dlp_store *store) { delete store; }

int dlp_store_add_rows(dlp_store *store, Id predicate, size_t arity,
                       const Id *data, size_t row_count, size_t *changed) {
    if (changed) *changed = 0;
    return guarded([&] {
        require(store && changed, "store or changed output is null");
        validate_rows(predicate, arity, data, row_count);
        Store &value = *store->value;
        value.find(predicate, arity);
        if (!row_count) return;
        auto found = value.relations.find(predicate);
        if (found == value.relations.end()) {
            auto relation = std::make_unique<Relation>(arity);
            value.mutate();
            found = value.relations.emplace(predicate, std::move(relation)).first;
        }
        Relation &relation = *found->second;
        PruneEmptyRelation cleanup{value, predicate, relation};
        for (size_t i = 0; i < row_count; ++i) {
            Row row = copy_row(arity ? data + i * arity : nullptr, arity);
            if (relation.contains(row)) continue;
            value.mutate();
            relation.add(std::move(row));
            ++*changed;
        }
    });
}

int dlp_store_discard_rows(dlp_store *store, Id predicate, size_t arity,
                           const Id *data, size_t row_count, size_t *changed) {
    if (changed) *changed = 0;
    return guarded([&] {
        require(store && changed, "store or changed output is null");
        validate_rows(predicate, arity, data, row_count);
        Store &value = *store->value;
        if (!value.find(predicate, arity)) return;
        Relation &relation = *value.relations.find(predicate)->second;
        PruneEmptyRelation cleanup{value, predicate, relation};
        for (size_t i = 0; i < row_count; ++i) {
            Row row = copy_row(arity ? data + i * arity : nullptr, arity);
            if (!relation.contains(row)) continue;
            value.mutate();
            relation.discard(row);
            ++*changed;
        }
    });
}

int dlp_store_clear(dlp_store *store) {
    return guarded([&] {
        require(store != nullptr, "store is null");
        if (!store->value->relations.empty()) {
            store->value->mutate();
            store->value->relations.clear();
        }
    });
}

int dlp_store_relation_info(dlp_store *store, Id predicate, size_t *arity,
                            size_t *row_count, int *exists) {
    return guarded([&] {
        require(store && arity && row_count && exists, "store or info output is null");
        require(predicate != 0, "predicate ID 0 is reserved");
        *arity = 0;
        *row_count = 0;
        *exists = 0;
        const auto found = store->value->relations.find(predicate);
        if (found != store->value->relations.end()) {
            *arity = found->second->arity;
            *row_count = found->second->rows.size();
            *exists = 1;
        }
    });
}

int dlp_store_contains(dlp_store *store, Id predicate, size_t arity,
                       const Id *row, int *contains) {
    return guarded([&] {
        require(store && contains, "store or contains output is null");
        validate_rows(predicate, arity, row, 1);
        *contains = 0;
        const Relation *relation = store->value->find(predicate, arity);
        if (relation) *contains = relation->contains(copy_row(row, arity));
    });
}

int dlp_store_lookup(dlp_store *store, Id predicate, size_t arity,
                      const Id *values, Id *output, size_t capacity, size_t *row_count) {
    if (row_count) *row_count = 0;
    return guarded([&] {
        require(store && row_count, "store or lookup count output is null");
        require(predicate != 0, "predicate ID 0 is reserved");
        require(arity == 0 || values, "lookup values are null");
        cells(1, arity);
        cells(capacity, arity);
        const Relation *relation = store->value->find(predicate, arity);
        if (!relation) return;
        const Selection selected = relation->lookup(copy_row(values, arity));
        *row_count = selected.size();
        if (!output && !capacity) return;
        require(capacity >= *row_count, "lookup output capacity is too small");
        require(arity == 0 || *row_count == 0 || output, "lookup output is null");
        if (arity == 0 || *row_count == 0) return;
        if (selected.singleton) {
            std::copy(selected.singleton->begin(), selected.singleton->end(), output);
        } else {
            for (const Row *row : *selected.bucket) {
                output = std::copy(row->begin(), row->end(), output);
            }
        }
    });
}

int dlp_query_new(dlp_store *store, dlp_store *delta_store,
                  const dlp_atom *atoms, size_t atom_count, size_t slot_count,
                  const Id *initial, int64_t delta_position, dlp_query **out) {
    if (out) *out = nullptr;
    return guarded([&] {
        require(store && out, "store or query output is null");
        require(atom_count == 0 || atoms, "query atoms are null");
        require(slot_count <= static_cast<size_t>(std::numeric_limits<int32_t>::max()),
                "query has too many binding slots");
        require(delta_position == -1 || (delta_position >= 0 &&
                    static_cast<uint64_t>(delta_position) < atom_count),
                "delta position is out of range");
        require(delta_position == -1 || delta_store, "delta store is null");
        auto handle = std::make_unique<dlp_query>();
        Query &query = handle->value;
        query.store = store->value;
        if (delta_position != -1) query.delta = delta_store->value;
        query.store_generation = query.store->generation;
        query.delta_generation = query.delta ? query.delta->generation : 0;
        query.slot_count = slot_count;
        query.initial = initial ? copy_row(initial, slot_count) : Row(slot_count, 0);
        query.atoms.reserve(atom_count);
        query.stack.reserve(atom_count);
        for (size_t i = 0; i < atom_count; ++i) {
            const dlp_atom &source = atoms[i];
            require(source.predicate != 0, "predicate ID 0 is reserved");
            require(source.arity == 0 || source.slots, "atom slots are null");
            cells(1, source.arity);
            Atom atom;
            atom.predicate = source.predicate;
            atom.store = delta_position >= 0 && i == static_cast<uint64_t>(delta_position)
                             ? query.delta.get() : query.store.get();
            atom.store->find(atom.predicate, source.arity);
            atom.constants.resize(source.arity, 0);
            atom.slots.reserve(source.arity);
            for (size_t j = 0; j < source.arity; ++j) {
                const int32_t slot = source.slots[j];
                require(slot == -1 || (slot >= 0 && static_cast<size_t>(slot) < slot_count),
                        "atom binding slot is out of range");
                atom.slots.push_back(slot);
                if (slot == -1) {
                    require(source.constants && source.constants[j] != 0,
                            "atom constant ID 0 is reserved or constants are null");
                    atom.constants[j] = source.constants[j];
                }
            }
            query.atoms.push_back(std::move(atom));
        }
        *out = handle.release();
    });
}

int dlp_query_next(dlp_query *query, Id *output, size_t capacity,
                   size_t *written, int *done) {
    if (written) *written = 0;
    if (done) *done = 1;
    const int result = guarded([&] {
        require(query && written && done, "query or batch output is null");
        Query &value = query->value;
        require(!value.failed, "query is invalid after an earlier error");
        require(capacity > 0, "query batch capacity must be positive");
        cells(capacity, value.slot_count);
        require(value.slot_count == 0 || output, "query binding output is null");
        require(value.store->generation == value.store_generation &&
                    (!value.delta || value.delta->generation == value.delta_generation),
                "native relation store mutated while query was active");
        size_t count = 0;
        while (count < capacity && value.advance(value.slot_count ? output + count * value.slot_count : nullptr))
            ++count;
        *written = count;
        *done = value.done;
    });
    if (result != 0 && query) {
        query->value.failed = true;
        query->value.done = true;
        // Destruction of iterators does not touch their invalidated buckets.
        query->value.stack.clear();
    }
    return result;
}

int dlp_query_stats(dlp_query *query, uint64_t *candidate_rows, uint64_t *body_matches) {
    return guarded([&] {
        require(query && candidate_rows && body_matches, "query or stats output is null");
        *candidate_rows = query->value.candidates;
        *body_matches = query->value.matches;
    });
}

void dlp_query_free(dlp_query *query) { delete query; }
} // extern "C"
