#include "native_windows.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
thread_local std::string last_error;
thread_local int32_t last_code = 0;
struct Failure : std::runtime_error {
    int code;
    Failure(int c, const char *message) : std::runtime_error(message), code(c) {}
};
void need(bool condition, int code, const char *message) {
    if (!condition)
        throw Failure(code, message);
}
template <class Work> int api(Work work) noexcept {
    last_error.clear();
    last_code = 0;
    try {
        work();
        return 0;
    } catch (const Failure &e) {
        last_code = e.code;
        try {
            last_error = e.what();
        } catch (...) {
        }
    } catch (const std::exception &e) {
        last_code = 7;
        try {
            last_error = e.what();
        } catch (...) {
        }
    } catch (...) {
        last_code = 7;
    }
    return -1;
}
std::string bytes(dlp_window_bytes input, uint64_t cap = uint64_t(INT64_MAX)) {
    need(input.data || !input.size, 1, "Null byte buffer");
    need(input.size <= cap, 2, "Byte input exceeds window budget");
    return input.size ? std::string(static_cast<const char *>(input.data), input.size)
                      : std::string();
}
dlp_window_bytes view(const std::string &value) { return {value.data(), value.size()}; }
struct Event {
    std::string id, key, row;
    int64_t time, revision;
    bool operator==(const Event &e) const {
        return id == e.id && key == e.key && row == e.row && time == e.time &&
               revision == e.revision;
    }
};
using Ptr = std::shared_ptr<const Event>;
using Events = std::map<std::string, Ptr>;
using Tombstones = std::map<std::string, std::pair<int64_t, int64_t>>;
using Offsets = std::map<std::string, int64_t>;
using Rows = std::vector<Ptr>;
struct Pool {
    std::atomic<size_t> live{0};
};
struct Lease {
    std::shared_ptr<Pool> pool;
    explicit Lease(std::shared_ptr<Pool> p) : pool(std::move(p)) {
        if (pool->live.fetch_add(1) >= 8) {
            pool->live.fetch_sub(1);
            throw Failure(2, "Free window exports before creating more");
        }
    }
    ~Lease() { pool->live.fetch_sub(1); }
};
bool before(const Event &a, const Event &b) {
    return std::tie(a.time, a.id) < std::tie(b.time, b.id);
}
void expose(const Ptr &event, dlp_window_event &out) {
    out = {view(event->id), view(event->key), view(event->row), event->time, event->revision};
}
struct State {
    Events events;
    Tombstones tombstones;
    Offsets offsets;
    int64_t end, watermark;
    uint64_t revision = 0, size = 0;
};
void valid(const dlp_window_config &c) {
    need(c.width > 0 && c.lateness >= 0 && c.watermark <= c.end && c.max_events > 0 &&
             c.max_events <= uint64_t(INT64_MAX) && c.max_bytes > 0 &&
             c.max_bytes <= uint64_t(INT64_MAX) && c.max_keys > 0 &&
             c.max_keys <= uint64_t(INT64_MAX) && c.predecessors <= 1 && c.allow_gaps <= 1,
         1, "Invalid window configuration");
}
Rows selected(const State &s, const dlp_window_config &c, uint32_t mode) {
    Rows result;
    __int128 start = __int128(s.end) - c.width;
    std::map<std::string, Ptr> previous;
    for (const auto &item : s.events) {
        const auto &e = item.second;
        if (mode == 2 || (__int128(e->time) >= start && e->time < s.end))
            result.push_back(e);
        if (mode == 1 && c.predecessors && __int128(e->time) < start) {
            auto p = previous.find(e->key);
            if (p == previous.end() || before(*p->second, *e))
                previous[e->key] = e;
        }
    }
    for (const auto &p : previous)
        result.push_back(p.second);
    return result;
}
void prune(State &s, const dlp_window_config &c, const std::string &context) {
    const __int128 start = __int128(s.end) - c.width;
    const __int128 cutoff = std::min(start, __int128(s.watermark) - c.lateness);
    std::map<std::string, Ptr> previous;
    if (c.predecessors)
        for (const auto &item : s.events) {
            const auto &e = item.second;
            if (__int128(e->time) < start) {
                auto p = previous.find(e->key);
                if (p == previous.end() || before(*p->second, *e))
                    previous[e->key] = e;
            }
        }
    for (auto i = s.events.begin(); i != s.events.end();) {
        auto p = previous.find(i->second->key);
        if (__int128(i->second->time) < cutoff && (p == previous.end() || p->second != i->second))
            i = s.events.erase(i);
        else
            ++i;
    }
    for (auto i = s.tombstones.begin(); i != s.tombstones.end();)
        if (__int128(i->second.second) < cutoff)
            i = s.tombstones.erase(i);
        else
            ++i;
    need(s.events.size() <= c.max_events && s.tombstones.size() <= c.max_events - s.events.size(),
         2, "Window event/tombstone capacity exceeded");
    std::set<std::string> keys;
    __int128 size = __int128(context.size()) * 4;
    for (const auto &item : s.events) {
        const auto &e = *item.second;
        keys.insert(e.key);
        size += (__int128(e.id.size()) + e.key.size() + e.row.size()) * 4 + 256;
    }
    for (const auto &item : s.tombstones)
        size += __int128(item.first.size()) * 4 + 128;
    for (const auto &item : s.offsets)
        size += __int128(item.first.size()) * 4 + 128;
    need(keys.size() <= c.max_keys, 2, "Window key/predecessor capacity exceeded");
    need(size <= c.max_bytes && s.offsets.size() <= 128, 2, "Window byte/source capacity exceeded");
    s.size = static_cast<uint64_t>(size);
}
bool equal_events(const Events &a, const Events &b) {
    if (a.size() != b.size())
        return false;
    auto x = a.begin(), y = b.begin();
    for (; x != a.end(); ++x, ++y)
        if (x->first != y->first || !(*x->second == *y->second))
            return false;
    return true;
}
Rows difference(const Rows &a, const Rows &b) {
    const auto compare = [](const Ptr &x, const Ptr &y) {
        return std::tie(x->id, x->time, x->key, x->row) < std::tie(y->id, y->time, y->key, y->row);
    };
    std::set<Ptr, decltype(compare)> rows(compare);
    rows.insert(b.begin(), b.end());
    Rows result;
    for (const auto &e : a)
        if (!rows.count(e))
            result.push_back(e);
    return result;
}
void next(const Rows &rows, size_t &position, dlp_window_event *out, size_t capacity, size_t *count,
          int *done) {
    need(out && capacity > 0 && count && done, 1, "Invalid export buffer");
    *count = std::min(capacity, rows.size() - position);
    for (size_t i = 0; i < *count; ++i)
        expose(rows[position++], out[i]);
    *done = position == rows.size();
}
} // namespace

struct dlp_window_store {
    dlp_window_config config;
    std::string context;
    State state;
    std::shared_ptr<Pool> pool = std::make_shared<Pool>();
};
struct dlp_window_rows {
    Lease lease;
    Rows rows;
    size_t position = 0;
    explicit dlp_window_rows(std::shared_ptr<Pool> p) : lease(std::move(p)) {}
};
struct dlp_window_change {
    Lease lease;
    uint64_t revision = 0;
    std::array<Rows, 6> rows;
    std::array<size_t, 6> positions{};
    explicit dlp_window_change(std::shared_ptr<Pool> p) : lease(std::move(p)) {}
};
namespace {
void commit(dlp_window_store *store, State candidate, dlp_window_change **output) {
    need(output, 1, "Null change output");
    *output = nullptr;
    prune(candidate, store->config, store->context);
    const auto &old = store->state;
    bool changed = !equal_events(old.events, candidate.events) ||
                   old.tombstones != candidate.tombstones || old.offsets != candidate.offsets ||
                   old.end != candidate.end || old.watermark != candidate.watermark;
    need(!changed || old.revision < uint64_t(INT64_MAX), 2, "Window revision exhausted");
    candidate.revision = old.revision + changed;
    auto change = std::make_unique<dlp_window_change>(store->pool);
    change->revision = candidate.revision;
    if (changed) {
        for (uint32_t mode = 0; mode < 2; ++mode) {
            const auto previous = selected(old, store->config, mode),
                       current = selected(candidate, store->config, mode);
            change->rows[mode * 2] = difference(current, previous);
            change->rows[mode * 2 + 1] = difference(previous, current);
        }
        for (const auto &pair : candidate.events) {
            auto p = old.events.find(pair.first);
            if (p == old.events.end() || !(*p->second == *pair.second))
                change->rows[4].push_back(pair.second);
        }
        for (const auto &pair : old.events) {
            auto p = candidate.events.find(pair.first);
            if (p == candidate.events.end() || !(*p->second == *pair.second))
                change->rows[5].push_back(pair.second);
        }
    }
    store->state = std::move(candidate);
    *output = change.release();
}
} // namespace
extern "C" {
uint32_t dlp_windows_abi() { return 1; }
const char *dlp_windows_error() { return last_error.c_str(); }
int32_t dlp_windows_error_code() { return last_code; }
int dlp_windows_new(const dlp_window_config *c, dlp_window_bytes context, dlp_window_store **out) {
    return api([&] {
        need(c && out, 1, "Null configuration/output");
        *out = nullptr;
        valid(*c);
        auto store = std::make_unique<dlp_window_store>();
        store->config = *c;
        store->context = bytes(context, c->max_bytes);
        store->state.end = c->end;
        store->state.watermark = c->watermark;
        prune(store->state, *c, store->context);
        *out = store.release();
    });
}
void dlp_windows_free(dlp_window_store *store) { delete store; }
int dlp_windows_info(dlp_window_store *s, dlp_window_info *out) {
    return api([&] {
        need(s && out, 1, "Null store/info");
        const auto &v = s->state;
        *out = {v.revision,       v.events.size(), v.tombstones.size(), v.size,
                v.offsets.size(), v.end,           v.watermark};
    });
}
int dlp_windows_config(dlp_window_store *s, dlp_window_config *out, dlp_window_bytes *context) {
    return api([&] {
        need(s && out && context, 1, "Null store/config");
        *out = s->config;
        out->end = s->state.end;
        out->watermark = s->state.watermark;
        *context = view(s->context);
    });
}
int dlp_windows_event(dlp_window_store *s, dlp_window_bytes id, dlp_window_event *out, int *found) {
    return api([&] {
        need(s && out && found, 1, "Null event lookup");
        auto p = s->state.events.find(bytes(id, s->config.max_bytes));
        *found = p != s->state.events.end();
        if (*found)
            expose(p->second, *out);
    });
}
int dlp_windows_predecessor(dlp_window_store *s, dlp_window_bytes id, dlp_window_event *out,
                            int *found) {
    return api([&] {
        need(s && out && found, 1, "Null predecessor lookup");
        auto p = s->state.events.find(bytes(id, s->config.max_bytes));
        need(p != s->state.events.end(), 1, "Unknown event identity");
        Ptr prior;
        for (const auto &item : s->state.events)
            if (item.second->key == p->second->key && before(*item.second, *p->second))
                if (!prior || before(*prior, *item.second))
                    prior = item.second;
        *found = bool(prior);
        if (prior)
            expose(prior, *out);
    });
}
int dlp_windows_offset(dlp_window_store *s, size_t index, dlp_window_bytes *source,
                       int64_t *offset) {
    return api([&] {
        need(s && source && offset && index < s->state.offsets.size(), 1, "Invalid offset index");
        auto p = s->state.offsets.begin();
        std::advance(p, index);
        *source = view(p->first);
        *offset = p->second;
    });
}
int dlp_windows_upsert(dlp_window_store *s, const dlp_window_event *input, dlp_window_bytes source,
                       int64_t offset, dlp_window_change **out) {
    return api([&] {
        need(s && input && out, 1, "Null upsert");
        *out = nullptr;
        need((__int128(input->id.size) + input->key.size + input->row.size) * 4 + 256 <=
                 s->config.max_bytes,
             2, "Event exceeds window byte budget");
        auto e = std::make_shared<Event>(
            Event{bytes(input->id, s->config.max_bytes), bytes(input->key, s->config.max_bytes),
                  bytes(input->row, s->config.max_bytes), input->time, input->revision});
        need(!e->id.empty() && e->revision >= 0, 1, "Invalid event identity/revision");
        std::string partition = bytes(source, s->config.max_bytes);
        need(partition.empty() ? offset == -1 : offset >= 0, 1,
             "Source and offset must be supplied together");
        State candidate = s->state;
        auto old = candidate.events.find(e->id);
        bool same = old != candidate.events.end() && *old->second == *e;
        if (!partition.empty()) {
            auto previous = candidate.offsets.find(partition);
            if (previous != candidate.offsets.end()) {
                if (offset <= previous->second) {
                    need(same, 5, "Offset replay differs from retained accepted event");
                    commit(s, std::move(candidate), out);
                    return;
                }
                need(s->config.allow_gaps || offset == previous->second + 1, 5,
                     "Source offset gap");
            }
            candidate.offsets[partition] = offset;
        }
        if (!same) {
            auto tombstone = candidate.tombstones.find(e->id);
            int64_t revision = old != candidate.events.end()             ? old->second->revision
                               : tombstone != candidate.tombstones.end() ? tombstone->second.first
                                                                         : -1;
            need(e->revision > revision, 4, "Changed event must have greater revision");
            int64_t oldest =
                old == candidate.events.end() ? e->time : std::min(e->time, old->second->time);
            need(__int128(oldest) >= __int128(candidate.watermark) - s->config.lateness, 3,
                 "Event/correction exceeds lateness");
            candidate.tombstones.erase(e->id);
            candidate.events[e->id] = std::move(e);
        }
        commit(s, std::move(candidate), out);
    });
}
int dlp_windows_remove(dlp_window_store *s, dlp_window_bytes input, int64_t revision,
                       dlp_window_change **out) {
    return api([&] {
        need(s && out && revision >= 0, 1, "Invalid removal");
        *out = nullptr;
        auto id = bytes(input, s->config.max_bytes);
        State candidate = s->state;
        auto tombstone = candidate.tombstones.find(id);
        if (tombstone != candidate.tombstones.end() && revision == tombstone->second.first) {
            commit(s, std::move(candidate), out);
            return;
        }
        auto old = candidate.events.find(id);
        need(old != candidate.events.end(), 5, "Cannot remove unknown/forgotten event");
        need(revision > old->second->revision, 4, "Removal must have greater revision");
        need(__int128(old->second->time) >= __int128(candidate.watermark) - s->config.lateness, 3,
             "Removal exceeds lateness");
        candidate.tombstones[id] = {revision, old->second->time};
        candidate.events.erase(old);
        commit(s, std::move(candidate), out);
    });
}
int dlp_windows_advance(dlp_window_store *s, int64_t end, int64_t watermark,
                        dlp_window_change **out) {
    return api([&] {
        need(s && out, 1, "Null advance");
        *out = nullptr;
        need(end >= s->state.end && watermark >= s->state.watermark && watermark <= end, 1,
             "Clocks must advance monotonically");
        State candidate = s->state;
        candidate.end = end;
        candidate.watermark = watermark;
        commit(s, std::move(candidate), out);
    });
}
int dlp_windows_forget(dlp_window_store *s, dlp_window_bytes key, dlp_window_change **out) {
    return api([&] {
        need(s && out, 1, "Null forget");
        *out = nullptr;
        auto value = bytes(key, s->config.max_bytes);
        State candidate = s->state;
        for (auto p = candidate.events.begin(); p != candidate.events.end();) {
            if (p->second->key == value)
                p = candidate.events.erase(p);
            else
                ++p;
        }
        commit(s, std::move(candidate), out);
    });
}
int dlp_windows_rows(dlp_window_store *s, uint32_t mode, dlp_window_rows **out) {
    return api([&] {
        need(s && out && mode <= 2, 1, "Invalid row export");
        *out = nullptr;
        auto rows = std::make_unique<dlp_window_rows>(s->pool);
        rows->rows = selected(s->state, s->config, mode);
        *out = rows.release();
    });
}
int dlp_windows_next(dlp_window_rows *rows, dlp_window_event *out, size_t capacity, size_t *count,
                     int *done) {
    return api([&] {
        need(rows, 1, "Null rows");
        next(rows->rows, rows->position, out, capacity, count, done);
    });
}
void dlp_windows_rows_free(dlp_window_rows *rows) { delete rows; }
int dlp_windows_change_next(dlp_window_change *change, uint32_t mode, dlp_window_event *out,
                            size_t capacity, size_t *count, int *done) {
    return api([&] {
        need(change && mode < 6, 1, "Invalid change stream");
        next(change->rows[mode], change->positions[mode], out, capacity, count, done);
    });
}
int dlp_windows_change_revision(dlp_window_change *change, uint64_t *out) {
    return api([&] {
        need(change && out, 1, "Null change revision");
        *out = change->revision;
    });
}
void dlp_windows_change_free(dlp_window_change *change) { delete change; }
}

namespace {
uint32_t crc32(const unsigned char *data, size_t size) {
    uint32_t crc = ~uint32_t(0);
    for (size_t i = 0; i < size; ++i) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1)));
    }
    return ~crc;
}
void number(std::string &out, uint64_t value) {
    for (unsigned i = 0; i < 8; ++i)
        out.push_back(char(value >> (i * 8)));
}
void string(std::string &out, const std::string &value) {
    number(out, value.size());
    out.append(value);
}
struct Reader {
    const unsigned char *data;
    size_t size, at = 0;
    uint64_t budget = 0, charged = 0;
    void charge(uint64_t value) {
        need(value <= budget - charged, 2, "Checkpoint exceeds retained byte budget");
        charged += value;
    }
    uint64_t number() {
        need(size - at >= 8, 6, "Truncated checkpoint number");
        uint64_t value = 0;
        for (unsigned i = 0; i < 8; ++i)
            value |= uint64_t(data[at++]) << (i * 8);
        return value;
    }
    int64_t signed_number() {
        auto value = number();
        int64_t result;
        std::memcpy(&result, &value, 8);
        return result;
    }
    std::string string(uint64_t cap) {
        auto length = number();
        need(length <= cap && length <= size - at, 6, "Invalid checkpoint string length");
        need(length <= (budget - charged) / 4, 2, "Checkpoint exceeds retained byte budget");
        charge(length * 4);
        std::string result(reinterpret_cast<const char *>(data + at), static_cast<size_t>(length));
        at += length;
        return result;
    }
};
std::string checkpoint(dlp_window_store *s) {
    std::string out("DLPWIN01", 8);
    const auto &c = s->config;
    const auto &state = s->state;
    for (auto value : {c.width, c.lateness, state.end, state.watermark})
        number(out, uint64_t(value));
    for (auto value : {c.max_events, c.max_bytes, c.max_keys, uint64_t(c.predecessors),
                       uint64_t(c.allow_gaps), state.revision})
        number(out, value);
    string(out, s->context);
    number(out, state.events.size());
    for (const auto &item : state.events) {
        const auto &e = *item.second;
        string(out, e.id);
        string(out, e.key);
        string(out, e.row);
        number(out, uint64_t(e.time));
        number(out, uint64_t(e.revision));
    }
    number(out, state.tombstones.size());
    for (const auto &item : state.tombstones) {
        string(out, item.first);
        number(out, uint64_t(item.second.first));
        number(out, uint64_t(item.second.second));
    }
    number(out, state.offsets.size());
    for (const auto &item : state.offsets) {
        string(out, item.first);
        number(out, uint64_t(item.second));
    }
    uint32_t crc = crc32(reinterpret_cast<const unsigned char *>(out.data()), out.size());
    for (unsigned i = 0; i < 4; ++i)
        out.push_back(char(crc >> (i * 8)));
    return out;
}
} // namespace
extern "C" {
int dlp_windows_checkpoint(dlp_window_store *s, void *output, size_t capacity, size_t *size) {
    return api([&] {
        need(s && size && (output || !capacity), 1, "Invalid checkpoint output");
        const auto data = checkpoint(s);
        *size = data.size();
        if (!output && !capacity)
            return;
        need(capacity >= data.size(), 2, "Checkpoint output buffer too small");
        std::memcpy(output, data.data(), data.size());
    });
}
int dlp_windows_restore(const void *input, size_t size, uint64_t checkpoint_cap, uint64_t event_cap,
                        uint64_t byte_cap, uint64_t key_cap, const dlp_window_bytes *expected,
                        dlp_window_store **out) {
    return api([&] {
        need(out, 1, "Null restore output");
        *out = nullptr;
        need(checkpoint_cap > 0 && event_cap > 0 && byte_cap > 0 && key_cap > 0, 1,
             "Invalid host checkpoint caps");
        need(size <= checkpoint_cap, 2, "Checkpoint exceeds host byte cap");
        need(input && size >= 8 + 10 * 8 + 4 && !std::memcmp(input, "DLPWIN01", 8), 6,
             "Invalid checkpoint header");
        const auto *data = static_cast<const unsigned char *>(input);
        uint32_t crc = 0;
        for (unsigned i = 0; i < 4; ++i)
            crc |= uint32_t(data[size - 4 + i]) << (i * 8);
        need(crc32(data, size - 4) == crc, 6, "Checkpoint checksum mismatch");
        Reader reader{data, size - 4, 8};
        auto store = std::make_unique<dlp_window_store>();
        auto &c = store->config;
        c.width = reader.signed_number();
        c.lateness = reader.signed_number();
        c.end = reader.signed_number();
        c.watermark = reader.signed_number();
        c.max_events = reader.number();
        c.max_bytes = reader.number();
        c.max_keys = reader.number();
        auto predecessors = reader.number(), gaps = reader.number();
        need(predecessors <= 1 && gaps <= 1, 6, "Invalid checkpoint policies");
        c.predecessors = uint32_t(predecessors);
        c.allow_gaps = uint32_t(gaps);
        valid(c);
        need(c.max_events <= event_cap && c.max_bytes <= byte_cap && c.max_keys <= key_cap, 2,
             "Checkpoint exceeds host retained-state caps");
        reader.budget = c.max_bytes;
        auto &state = store->state;
        state.end = c.end;
        state.watermark = c.watermark;
        state.revision = reader.number();
        need(state.revision <= uint64_t(INT64_MAX), 6, "Invalid stored revision");
        store->context = reader.string(c.max_bytes);
        if (expected)
            need(store->context == bytes(*expected, byte_cap), 5,
                 "Checkpoint context does not match");
        auto events = reader.number();
        need(events <= c.max_events, 2, "Checkpoint record cap exceeded");
        std::set<std::string> keys;
        for (uint64_t i = 0; i < events; ++i) {
            reader.charge(256);
            auto e = std::make_shared<Event>();
            e->id = reader.string(c.max_bytes);
            e->key = reader.string(c.max_bytes);
            e->row = reader.string(c.max_bytes);
            keys.insert(e->key);
            need(keys.size() <= c.max_keys, 2, "Checkpoint key capacity exceeded");
            e->time = reader.signed_number();
            e->revision = reader.signed_number();
            need(!e->id.empty() && e->revision >= 0 && state.events.emplace(e->id, e).second, 6,
                 "Invalid/duplicate checkpoint event");
        }
        auto tombstones = reader.number();
        need(tombstones <= c.max_events - events, 2, "Checkpoint tombstone cap exceeded");
        for (uint64_t i = 0; i < tombstones; ++i) {
            reader.charge(128);
            auto id = reader.string(c.max_bytes);
            auto revision = reader.signed_number(), time = reader.signed_number();
            need(!id.empty() && revision >= 0 && !state.events.count(id) &&
                     state.tombstones.emplace(id, std::make_pair(revision, time)).second,
                 6, "Invalid/duplicate checkpoint tombstone");
        }
        auto sources = reader.number();
        need(sources <= 128, 2, "Checkpoint source cap exceeded");
        for (uint64_t i = 0; i < sources; ++i) {
            reader.charge(128);
            auto source = reader.string(c.max_bytes);
            auto offset = reader.signed_number();
            need(!source.empty() && offset >= 0 && state.offsets.emplace(source, offset).second, 6,
                 "Invalid/duplicate checkpoint offset");
        }
        need(reader.at == reader.size, 6, "Trailing checkpoint bytes");
        prune(state, c, store->context);
        need(state.events.size() == events && state.tombstones.size() == tombstones, 6,
             "Checkpoint violates retention policy");
        *out = store.release();
    });
}
}
