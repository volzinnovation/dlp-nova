#include "native_query.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <list>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {
thread_local std::string error;
thread_local int32_t status = 0;
struct Failure : std::runtime_error {
    int32_t code;
    Failure(int32_t c, const std::string &s) : std::runtime_error(s), code(c) {}
};
void require(bool condition, const char *message, int32_t code = 2) {
    if (!condition)
        throw Failure(code, message);
}
template <class F> int protect(F function) noexcept {
    try {
        status = 0;
        error.clear();
        function();
        status = 0;
        error.clear();
        return 0;
    } catch (const Failure &e) {
        status = e.code;
        try {
            error = e.what();
        } catch (...) {
        }
    } catch (const std::bad_alloc &) {
        status = 6;
        try {
            error = "native query allocation limit";
        } catch (...) {
        }
    } catch (const std::exception &e) {
        status = 7;
        try {
            error = e.what();
        } catch (...) {
        }
    } catch (...) {
        status = 7;
        try {
            error = "unknown native query failure";
        } catch (...) {
        }
    }
    return -1;
}
void domain_check(int code) {
    if (code)
        throw Failure(dlp_domain_context_last_status(), dlp_domain_last_error());
}
using ID = uint64_t;
using Row = std::vector<ID>;
using Binding = Row;
struct Relation {
    size_t arity = 0;
    std::set<Row> rows;
    std::vector<std::unordered_map<ID, std::vector<const Row *>>> columns;
    explicit Relation(size_t n = 0) : arity(n), columns(n) {}
    Relation(const Relation &other) : Relation(other.arity) {
        for (const auto &r : other.rows)
            add(r);
    }
    Relation(Relation &&) noexcept = default;
    Relation &operator=(Relation &&) noexcept = default;
    Relation &operator=(const Relation &other) {
        Relation copied(other);
        *this = std::move(copied);
        return *this;
    }
    bool add(const Row &row) {
        require(row.size() == arity, "relation arity mismatch", 8);
        auto inserted = rows.insert(row);
        if (!inserted.second)
            return false;
        for (size_t i = 0; i < arity; ++i)
            columns[i][row[i]].push_back(&*inserted.first);
        return true;
    }
    bool remove(const Row &row) {
        auto found = rows.find(row);
        if (found == rows.end())
            return false;
        for (size_t i = 0; i < arity; ++i) {
            auto bucket = columns[i].find(row[i]);
            auto &values = bucket->second;
            values.erase(std::remove(values.begin(), values.end(), &*found), values.end());
            if (values.empty())
                columns[i].erase(bucket);
        }
        rows.erase(found);
        return true;
    }
};
using Relations = std::map<ID, Relation>;
struct Term {
    dlp_domain_value value{};
    ID domain = 0, neq_key = 0;
    uint32_t neq_group = 0;
    uint32_t roles = 0;
    int32_t decode_status = 1;
    bool canonical = false, generated = false;
    std::string order;
};
// Compare fields rather than struct padding; IEEE signed zero is significant
// for canonical RDF output identities even though ordered comparisons tie.
std::string value_key(const dlp_domain_value &v) {
    std::string key;
    auto append = [&](const auto &x) { key.append(reinterpret_cast<const char *>(&x), sizeof(x)); };
    append(v.tag);
    append(v.a);
    append(v.b);
    append(v.c);
    append(v.x);
    append(v.y);
    return key;
}
std::string generated_order(const dlp_domain_value &v) {
    // For an equal input scalar, the host supplied its exact canonical output
    // key before execution. This fallback is used for new outputs only: equal
    // canonical same-type outputs are one ID, distinct numeric types compare
    // datatype prefixes. IEEE +/-zero is the sole same-type alternate identity.
    if (v.tag == 12) {
        return std::string("value\0dlp_reasoner.domains.Quantity\0", 36) +
               (v.c == 2 ? "Quantity(value=IntegerValue(" : "Quantity(value=DecimalValue(");
    }
    const char *datatype = nullptr;
    switch (v.tag) {
    case 1:
        datatype = "boolean";
        break;
    case 2:
        datatype = "integer";
        break;
    case 3:
        datatype = "decimal";
        break;
    case 4:
        datatype = "double";
        break;
    case 5:
        datatype = "date";
        break;
    case 6:
        datatype = "dateTimeStamp";
        break;
    case 7:
        datatype = "time";
        break;
    case 8:
        datatype = "dayTimeDuration";
        break;
    default:
        return {};
    }
    std::string key("literal\0", 8);
    key += "http://www.w3.org/2001/XMLSchema#";
    key += datatype;
    key.append("\0\0", 2);
    if (v.tag == 4 && v.x == 0)
        key += std::signbit(v.x) ? "-0.0" : "0.0";
    return key;
}
struct Node {
    uint32_t kind = 0, opcode = 0;
    ID predicate = 0;
    std::vector<dlp_qx_arg> args;
    dlp_qx_arg output{-1, 0};
    std::vector<int32_t> groups;
    int32_t value_slot = -1;
};
struct Rule {
    ID stratum, predicate;
    std::vector<dlp_qx_arg> head;
    Binding initial;
    std::vector<Node> body;
};
struct Memo {
    dlp_domain_value value{};
    std::list<std::string>::iterator age;
    size_t bytes;
};
} // namespace

struct dlp_qx_context {
    dlp_qx_limits limits;
    dlp_qx_stats stats{};
    Relations source, candidate;
    size_t source_count = 0;
    std::map<ID, Term> terms;
    std::unordered_map<std::string, ID> canonical;
    std::unordered_map<std::string, std::string> canonical_orders;
    std::map<std::string, Memo> memo;
    std::list<std::string> memo_age;
    size_t memo_bytes = 0;
    ID memo_capacity = 4096, memo_byte_capacity = 4 * 1024 * 1024;
    std::vector<Rule> rules;
    std::set<ID> heads;
    dlp_domain_context *domains = nullptr;
    ID next_term = 1;
    bool begun = false, complete = false, running = false, poisoned = false;
    dlp_qx_control control = nullptr;
    void *user = nullptr;
    explicit dlp_qx_context(dlp_qx_limits l) : limits(l) {
        domain_check(dlp_domain_context_new(std::max<ID>(4, l.max_terms), &domains));
    }
    ~dlp_qx_context() { dlp_domain_context_free(domains); }
    void check(bool force = false) {
        require(stats.work < limits.max_work, "max_native_work exceeded", 6);
        ++stats.work;
        if ((force || stats.work % 256 == 0) && control && control(user))
            throw Failure(9, "native query cancelled or deadline exceeded");
    }
    void validate_plan() {
        std::map<ID, ID> levels;
        std::map<ID, size_t> arities;
        for (const auto &relation : source)
            arities.emplace(relation.first, relation.second.arity);
        auto arity = [&](ID predicate, size_t size) {
            auto found = arities.emplace(predicate, size);
            require(found.second || found.first->second == size, "plan relation arity mismatch", 8);
        };
        for (const auto &rule : rules) {
            arity(rule.predicate, rule.head.size());
            auto found = levels.emplace(rule.predicate, rule.stratum);
            require(found.second || found.first->second == rule.stratum,
                    "one query predicate cannot have multiple strata");
        }
        for (const auto &rule : rules) {
            std::vector<bool> bound;
            for (auto id : rule.initial)
                bound.push_back(id != 0);
            auto ready = [&](const dlp_qx_arg &arg) { return arg.slot < 0 || bound.at(arg.slot); };
            auto bind = [&](const dlp_qx_arg &arg) {
                if (arg.slot >= 0)
                    bound.at(arg.slot) = true;
            };
            const bool generator = std::any_of(rule.body.begin(), rule.body.end(),
                                               [](const Node &node) { return node.kind == 4; });
            for (const auto &node : rule.body) {
                if (node.kind == 0 || node.kind == 5) {
                    arity(node.predicate, node.args.size());
                    auto dependency = levels.find(node.predicate);
                    if (dependency != levels.end()) {
                        require(dependency->second <= rule.stratum,
                                "query dependency must precede its consumer");
                        require(!(generator || node.kind == 5) || dependency->second < rule.stratum,
                                "MIN and generated values require a preceding complete stratum");
                    }
                    if (node.kind == 0) {
                        for (const auto &arg : node.args)
                            bind(arg);
                    } else {
                        std::set<int32_t> source_slots;
                        for (const auto &arg : node.args)
                            if (arg.slot >= 0)
                                source_slots.insert(arg.slot);
                        require(source_slots.count(node.value_slot),
                                "MIN value is absent from its source");
                        require(node.output.slot >= 0 && !source_slots.count(node.output.slot),
                                "MIN output must be distinct from its source variables");
                        require(std::set<int32_t>(node.groups.begin(), node.groups.end()).size() ==
                                    node.groups.size(),
                                "duplicate MIN group variable");
                        for (auto slot : source_slots)
                            require(!bound.at(slot) || rule.initial.at(slot) ||
                                        std::find(node.groups.begin(), node.groups.end(), slot) !=
                                            node.groups.end(),
                                    "correlated MIN source variable is not an explicit initial "
                                    "parameter");
                        for (auto slot : node.groups) {
                            require(source_slots.count(slot),
                                    "MIN group variable absent from its source");
                            bound.at(slot) = true;
                        }
                        bind(node.output);
                    }
                } else if (node.kind == 1) {
                    require(ready(node.args[0]) || ready(node.args[1]),
                            "EQ needs at least one bound argument");
                    for (const auto &arg : node.args)
                        bind(arg);
                } else {
                    if (node.kind == 3 || node.kind == 4) {
                        const auto op = node.opcode;
                        const bool known = (op >= 1 && op <= 10) || (op >= 20 && op <= 28) ||
                                           (op >= 30 && op <= 37) || (op >= 40 && op <= 42);
                        require(known, "unavailable native query opcode", 5);
                        const size_t arity = op == 30 ? 1 : (op == 4 || op == 42 ? 3 : 2);
                        require(node.args.size() == arity, "native query operation arity mismatch",
                                8);
                        const bool boolean = (op >= 1 && op <= 3) || (op >= 6 && op <= 8) ||
                                             (op >= 24 && op <= 28) || op == 31 || op == 35 ||
                                             op == 36 || op == 42;
                        require(node.kind != 3 || boolean, "filter operation must return Boolean",
                                1);
                    }
                    for (const auto &arg : node.args)
                        require(ready(arg), "unbound operation or NEQ argument");
                    if (node.kind == 4)
                        bind(node.output);
                }
            }
            for (const auto &arg : rule.head)
                require(ready(arg), "unsafe native query head variable");
        }
    }
    ID value(const dlp_qx_arg &arg, const Binding &binding) const {
        ID result = arg.slot < 0 ? arg.constant : binding.at(static_cast<size_t>(arg.slot));
        require(result != 0, "unbound native query argument");
        return result;
    }
    ID domain_id(ID id) {
        auto found = terms.find(id);
        require(found != terms.end(), "unknown native query term");
        auto &term = found->second;
        if (!term.value.tag)
            throw Failure(term.decode_status, "invalid or unsupported scalar query argument");
        if (!term.domain)
            domain_check(dlp_domain_context_intern(domains, &term.value, 1, &term.domain));
        return term.domain;
    }
    bool agree(ID left, ID right) {
        if (left == right)
            return true;
        try {
            int32_t order = 0;
            domain_check(
                dlp_domain_context_compare(domains, domain_id(left), domain_id(right), &order));
            return order == 0;
        } catch (const Failure &e) {
            if (e.code == 6 || e.code == 7)
                throw;
            return false;
        }
    }
    bool assign(Binding &binding, const dlp_qx_arg &arg, ID actual) {
        if (arg.slot < 0)
            return agree(arg.constant, actual);
        auto &slot = binding.at(static_cast<size_t>(arg.slot));
        if (slot)
            return agree(slot, actual);
        slot = actual;
        return true;
    }
    void append(std::vector<Binding> &result, Binding binding) {
        require(result.size() < limits.max_bindings, "max_bindings exceeded", 6);
        result.push_back(std::move(binding));
    }
    template <class Consume> void join(const Node &node, const Binding &binding, Consume consume) {
        auto found = candidate.find(node.predicate);
        if (found == candidate.end())
            return;
        const auto &relation = found->second;
        require(relation.arity == node.args.size(), "relation arity mismatch", 8);
        const std::vector<const Row *> *bucket = nullptr;
        for (size_t i = 0; i < node.args.size(); ++i) {
            const auto &arg = node.args[i];
            ID bound = arg.slot < 0 ? arg.constant : binding.at(static_cast<size_t>(arg.slot));
            if (!bound)
                continue;
            auto column = relation.columns[i].find(bound);
            if (column == relation.columns[i].end())
                return;
            if (!bucket || column->second.size() < bucket->size())
                bucket = &column->second;
        }
        auto match = [&](const Row &row) {
            check();
            ++stats.candidate_rows;
            Binding extended = binding;
            for (size_t i = 0; i < row.size(); ++i) {
                auto arg = node.args[i];
                if (arg.slot < 0) {
                    if (row[i] != arg.constant)
                        return;
                } else {
                    auto &slot = extended.at(static_cast<size_t>(arg.slot));
                    if (slot && slot != row[i])
                        return;
                    slot = row[i];
                }
            }
            ++stats.body_matches;
            consume(std::move(extended));
        };
        if (bucket) {
            for (const auto *row : *bucket)
                match(*row);
        } else {
            for (const auto &row : relation.rows)
                match(row);
        }
    }
    bool different(ID left, ID right, ID predicate) {
        auto explicit_rows = candidate.find(predicate);
        if (explicit_rows != candidate.end() &&
            (explicit_rows->second.rows.count(Row{left, right}) ||
             explicit_rows->second.rows.count(Row{right, left})))
            return true;
        const auto &a = terms.at(left), &b = terms.at(right);
        if (!a.neq_group || !b.neq_group)
            return false;
        if (a.neq_group != b.neq_group)
            return true;
        if (a.neq_key && b.neq_key)
            return a.neq_key != b.neq_key;
        if (a.neq_group == 1) {
            // Unsupported out-of-range RDF numbers cannot equal a generated
            // in-range scalar. Input/input equality is supplied by neq_key.
            if (!a.value.tag || !b.value.tag)
                return true;
            return !agree(left, right);
        }
        if (a.neq_group == 2)
            return a.value.a != b.value.a;
        return false;
    }
    ID operation(const Node &node, const Binding &binding) {
        std::vector<ID> arguments;
        std::string memo_key(reinterpret_cast<const char *>(&node.opcode), sizeof(node.opcode));
        for (size_t i = 0; i < node.args.size(); ++i) {
            const ID id = value(node.args[i], binding);
            auto &term = terms.at(id);
            dlp_domain_value decoded{};
            ID input_id = 0;
            if (node.opcode == 4 && i == 2) {
                require(term.roles & 2, "only march1 anniversary policy is available", 5);
                decoded.tag = 11;
                decoded.a = 1;
                domain_check(dlp_domain_context_intern(domains, &decoded, 1, &input_id));
            } else if (node.opcode == 32 && i == 1) {
                require(term.roles & 1, "quantity unit requires a string, IRI or literal", 1);
                require((term.roles >> 2) != 0, "unknown quantity unit profile", 5);
                decoded.tag = 13;
                decoded.a = term.roles >> 2;
                domain_check(dlp_domain_context_intern(domains, &decoded, 1, &input_id));
            } else {
                input_id = domain_id(id);
                decoded = term.value;
            }
            arguments.push_back(input_id);
            memo_key += value_key(decoded);
        }
        ID output = 0;
        int32_t row_status = 0;
        dlp_domain_value decoded{};
        int32_t decoded_status = 0;
        ++stats.operation_rows;
        auto saved = memo.find(memo_key);
        if (saved != memo.end()) {
            decoded = saved->second.value;
            ++stats.memo_hits;
            memo_age.splice(memo_age.end(), memo_age, saved->second.age);
        } else {
            domain_check(dlp_domain_context_evaluate(domains, node.opcode, arguments.data(), 1,
                                                     arguments.size(), &output, &row_status));
            ++stats.domain_evaluations;
            if (row_status)
                throw Failure(row_status, "native scalar query operation failed");
            domain_check(dlp_domain_context_get(domains, &output, 1, &decoded, &decoded_status));
            require(decoded_status == 0, "native scalar output cannot be retrieved", 7);
        }
        // Python's canonical xsd:dateTimeStamp serializer supports years 1..9999.
        if (decoded.tag == 6)
            require(decoded.a >= INT64_C(-62135596800000000) &&
                        decoded.a <= INT64_C(253402300799999999),
                    "instant output exceeds the supported lexical year range", 3);
        if (saved == memo.end()) {
            const size_t bytes = 512 + 2 * memo_key.size() + sizeof(dlp_domain_value);
            if (memo_capacity && bytes <= memo_byte_capacity) {
                while (!memo.empty() &&
                       (memo.size() >= memo_capacity || memo_bytes + bytes > memo_byte_capacity)) {
                    auto old = memo.find(memo_age.front());
                    memo_bytes -= old->second.bytes;
                    memo.erase(old);
                    memo_age.pop_front();
                    ++stats.memo_evictions;
                }
                // Insert map first; on age allocation failure erase it before
                // propagation so the persistent memo remains usable next run.
                auto added = memo.emplace(memo_key, Memo{decoded, {}, bytes}).first;
                try {
                    memo_age.push_back(memo_key);
                } catch (...) {
                    memo.erase(added);
                    throw;
                }
                added->second.age = std::prev(memo_age.end());
                memo_bytes += bytes;
            } else
                ++stats.memo_bypasses;
        }
        const auto key = value_key(decoded);
        auto existing = canonical.find(key);
        if (existing != canonical.end())
            return existing->second;
        require(terms.size() < limits.max_terms, "max_terms exceeded by generated values", 6);
        require(next_term < std::numeric_limits<ID>::max(), "native query term ID overflow", 3);
        const ID id = next_term++;
        Term term;
        term.value = decoded;
        term.domain = output;
        term.decode_status = 0;
        term.canonical = term.generated = true;
        auto order = canonical_orders.find(key);
        term.order = order == canonical_orders.end() ? generated_order(decoded) : order->second;
        term.neq_group = decoded.tag == 1 ? 2 : (decoded.tag == 2 || decoded.tag == 3 ? 1 : 0);
        terms.emplace(id, term);
        canonical.emplace(key, id);
        ++stats.generated_terms;
        return id;
    }
    std::vector<Binding> solve(const Rule &rule) {
        std::vector<Binding> bindings{rule.initial};
        for (const auto &node : rule.body) {
            if (bindings.empty())
                break;
            std::vector<Binding> following;
            for (const auto &binding : bindings) {
                check();
                if (node.kind == 0) {
                    join(node, binding, [&](Binding row) { append(following, std::move(row)); });
                } else if (node.kind == 1) {
                    const auto left = node.args[0], right = node.args[1];
                    const ID a = left.slot < 0 ? left.constant : binding.at(left.slot);
                    const ID b = right.slot < 0 ? right.constant : binding.at(right.slot);
                    require(a || b, "EQ needs one bound argument");
                    if (a && b) {
                        if (a == b)
                            append(following, binding);
                    } else {
                        auto row = binding;
                        row.at(a ? right.slot : left.slot) = a ? a : b;
                        append(following, std::move(row));
                    }
                } else if (node.kind == 2) {
                    if (different(value(node.args[0], binding), value(node.args[1], binding),
                                  node.predicate))
                        append(following, binding);
                } else if (node.kind == 3 || node.kind == 4) {
                    ID output = operation(node, binding);
                    if (node.kind == 3) {
                        const auto &v = terms.at(output).value;
                        require(v.tag == 1, "filter returned a non-Boolean value", 1);
                        if (v.a)
                            append(following, binding);
                    } else {
                        auto row = binding;
                        if (assign(row, node.output, output))
                            append(following, std::move(row));
                    }
                } else {
                    std::map<Row, ID> groups;
                    size_t matches = 0;
                    join(node, binding, [&](const Binding &row) {
                        require(matches++ < limits.max_bindings,
                                "max_bindings exceeded by MIN source", 6);
                        const ID actual = row.at(node.value_slot);
                        int32_t order = 0;
                        domain_check(dlp_domain_context_compare(domains, domain_id(actual),
                                                                domain_id(actual), &order));
                        Row key;
                        for (auto slot : node.groups)
                            key.push_back(row.at(slot));
                        auto previous = groups.find(key);
                        if (previous == groups.end())
                            groups.emplace(std::move(key), actual);
                        else {
                            domain_check(dlp_domain_context_compare(
                                domains, domain_id(actual), domain_id(previous->second), &order));
                            if (order == 0 && actual != previous->second)
                                require(!terms.at(actual).order.empty() &&
                                            !terms.at(previous->second).order.empty(),
                                        "MIN tie requires stable RDF identity metadata", 5);
                            if (order < 0 || (order == 0 && terms.at(actual).order <
                                                                terms.at(previous->second).order))
                                previous->second = actual;
                        }
                    });
                    for (const auto &group : groups) {
                        auto row = binding;
                        bool valid = true;
                        for (size_t i = 0; i < node.groups.size(); ++i)
                            if (!assign(row, dlp_qx_arg{node.groups[i], 0}, group.first[i])) {
                                valid = false;
                                break;
                            }
                        if (valid && assign(row, node.output, group.second))
                            append(following, std::move(row));
                    }
                }
            }
            bindings = std::move(following);
        }
        return bindings;
    }
};

extern "C" {
uint32_t dlp_qx_abi_version(void) { return 1; }
const char *dlp_qx_last_error(void) { return error.c_str(); }
int32_t dlp_qx_last_status(void) { return status; }
int dlp_qx_new(const dlp_qx_limits *limits, dlp_qx_context **out) {
    if (out)
        *out = nullptr;
    return protect([&] {
        require(limits && out, "null query context arguments");
        require(limits->max_rows && limits->max_bindings && limits->max_rounds &&
                    limits->max_terms && limits->max_work,
                "native query limits must be positive");
        *out = new dlp_qx_context(*limits);
    });
}
void dlp_qx_free(dlp_qx_context *ctx) { delete ctx; }
int dlp_qx_rows(dlp_qx_context *ctx, ID predicate, size_t arity, const ID *rows, size_t count,
                int add) {
    const int code = protect([&] {
        require(ctx && !ctx->running && !ctx->poisoned && predicate && arity <= 4096,
                "invalid or poisoned source row context");
        require(count <= ctx->limits.max_rows && (!count || !arity || rows),
                "invalid source row buffer", 6);
        require(!arity || count <= std::numeric_limits<size_t>::max() / arity,
                "row buffer size overflow", 3);
        ctx->complete = false;
        for (size_t i = 0; i < count; ++i) {
            Row row;
            if (arity)
                row.assign(rows + i * arity, rows + (i + 1) * arity);
            require(std::all_of(row.begin(), row.end(), [](ID x) { return x != 0; }),
                    "zero stored term ID");
            auto found = ctx->source.find(predicate);
            if (found != ctx->source.end())
                require(found->second.arity == arity, "source arity mismatch", 8);
            if (add) {
                if (found == ctx->source.end())
                    found = ctx->source.emplace(predicate, Relation(arity)).first;
                if (!found->second.rows.count(row)) {
                    require(ctx->source_count < ctx->limits.max_rows, "max_rows exceeded by source",
                            6);
                    found->second.add(row);
                    ++ctx->source_count;
                    ++ctx->stats.input_additions;
                }
            } else if (found != ctx->source.end() && found->second.remove(row)) {
                --ctx->source_count;
                ++ctx->stats.input_removals;
                if (found->second.rows.empty())
                    ctx->source.erase(found);
            }
        }
    });
    if (code && ctx && !ctx->running) {
        ctx->poisoned = true;
        ctx->complete = ctx->begun = false;
    }
    return code;
}
int dlp_qx_begin(dlp_qx_context *ctx) {
    const int code = protect([&] {
        require(ctx && !ctx->running && !ctx->poisoned, "query context unavailable or poisoned");
        ctx->complete = ctx->begun = false;
        ctx->candidate.clear();
        ctx->rules.clear();
        ctx->heads.clear();
        ctx->terms.clear();
        ctx->canonical.clear();
        ctx->canonical_orders.clear();
        ctx->next_term = 1;
        ctx->stats = {};
        domain_check(dlp_domain_context_clear(ctx->domains));
        ctx->begun = true;
    });
    if (code && ctx && !ctx->running)
        ctx->begun = ctx->complete = false;
    return code;
}
int dlp_qx_term(dlp_qx_context *ctx, ID id, const dlp_domain_value *value, int32_t decode_status,
                int canonical, uint32_t neq_group, ID neq_key) {
    const int code = protect([&] {
        require(ctx && ctx->begun && !ctx->running && id && id < std::numeric_limits<ID>::max() &&
                    value,
                "invalid native term arguments");
        require(!ctx->terms.count(id), "duplicate native term ID");
        require(ctx->terms.size() < ctx->limits.max_terms, "max_terms exceeded", 6);
        require(decode_status >= 0 && decode_status <= 8 && neq_group <= 4,
                "invalid native term metadata");
        Term term;
        term.value = *value;
        term.decode_status = decode_status ? decode_status : 1;
        term.canonical = canonical != 0;
        term.neq_group = neq_group;
        term.neq_key = neq_key;
        ctx->terms.emplace(id, term);
        ctx->next_term = std::max(ctx->next_term, id + 1);
        if (canonical && value->tag)
            ctx->canonical.emplace(value_key(*value), id);
    });
    if (code && ctx && !ctx->running)
        ctx->begun = ctx->complete = false;
    return code;
}
int dlp_qx_term_order(dlp_qx_context *ctx, ID id, const char *identity, size_t size,
                      const char *canonical, size_t canonical_size) {
    const int code = protect([&] {
        require(ctx && ctx->begun && !ctx->running && ctx->terms.count(id),
                "unknown term or unavailable query builder");
        require(size <= 32768 && canonical_size <= 32768, "MIN identity metadata exceeds capacity",
                6);
        require((!size || identity) && (!canonical_size || canonical),
                "null MIN identity metadata");
        auto &term = ctx->terms.at(id);
        term.order = size ? std::string(identity, size) : std::string();
        if (canonical_size && term.value.tag)
            ctx->canonical_orders[value_key(term.value)] = std::string(canonical, canonical_size);
    });
    if (code && ctx && !ctx->running)
        ctx->begun = ctx->complete = false;
    return code;
}
int dlp_qx_term_roles(dlp_qx_context *ctx, ID id, uint32_t flags) {
    const int code = protect([&] {
        require(ctx && ctx->begun && !ctx->running && ctx->terms.count(id),
                "unknown term or unavailable query builder");
        require(flags <= 15 && (!(flags >> 2) || (flags & 1)), "invalid argument role flags");
        ctx->terms.at(id).roles = flags;
    });
    if (code && ctx && !ctx->running)
        ctx->begun = ctx->complete = false;
    return code;
}
int dlp_qx_memo_limits(dlp_qx_context *ctx, ID entries, ID bytes) {
    return protect([&] {
        require(ctx && !ctx->running, "query context unavailable");
        ctx->memo_capacity = entries;
        ctx->memo_byte_capacity = bytes;
        while (!ctx->memo.empty() && (ctx->memo.size() > entries || ctx->memo_bytes > bytes)) {
            auto old = ctx->memo.find(ctx->memo_age.front());
            ctx->memo_bytes -= old->second.bytes;
            ctx->memo.erase(old);
            ctx->memo_age.pop_front();
            ++ctx->stats.memo_evictions;
        }
    });
}
int dlp_qx_rule(dlp_qx_context *ctx, ID stratum, ID predicate, size_t arity, const dlp_qx_arg *head,
                size_t slots, const ID *initial, const dlp_qx_node *body, size_t count) {
    const int code = protect([&] {
        require(ctx && ctx->begun && !ctx->running && predicate, "query plan unavailable");
        require(arity <= 4096 && slots <= 4096 && count <= 10000 && ctx->rules.size() < 100000,
                "native query plan capacity exceeded", 6);
        require((!arity || head) && (!count || body) && (!slots || initial),
                "null native plan buffer");
        require(ctx->rules.empty() || ctx->rules.back().stratum <= stratum,
                "query strata must be ordered");
        auto valid_arg = [&](const dlp_qx_arg &a) {
            require(a.slot >= -1 && (a.slot < 0 ? ctx->terms.count(a.constant) != 0
                                                : static_cast<size_t>(a.slot) < slots),
                    "invalid native plan slot/constant");
        };
        Rule rule{stratum, predicate, {}, {}, {}};
        if (arity)
            rule.head.assign(head, head + arity);
        if (slots)
            rule.initial.assign(initial, initial + slots);
        for (auto id : rule.initial)
            require(!id || ctx->terms.count(id), "unknown initial value");
        for (const auto &arg : rule.head)
            valid_arg(arg);
        for (size_t i = 0; i < count; ++i) {
            const auto &source = body[i];
            require(source.kind <= 5 && source.arity <= 4096 && (!source.arity || source.args),
                    "unsupported query plan node", 5);
            require((source.kind != 1 && source.kind != 2) || source.arity == 2,
                    "EQ/NEQ arity must be two", 8);
            Node node;
            node.kind = source.kind;
            node.opcode = source.opcode;
            node.predicate = source.predicate;
            if (source.arity)
                node.args.assign(source.args, source.args + source.arity);
            for (const auto &arg : node.args)
                valid_arg(arg);
            if (source.kind == 0 || source.kind == 2 || source.kind == 5)
                require(source.predicate, "zero predicate");
            if (source.kind == 4 || source.kind == 5) {
                valid_arg(source.output);
                node.output = source.output;
            }
            if (source.kind == 5) {
                require(source.group_count <= slots && (!source.group_count || source.groups),
                        "invalid MIN groups");
                if (source.group_count)
                    node.groups.assign(source.groups, source.groups + source.group_count);
                for (auto slot : node.groups)
                    require(slot >= 0 && static_cast<size_t>(slot) < slots,
                            "invalid MIN group slot");
                require(source.value_slot >= 0 && static_cast<size_t>(source.value_slot) < slots,
                        "invalid MIN value slot");
                node.value_slot = source.value_slot;
            }
            rule.body.push_back(std::move(node));
        }
        ctx->rules.push_back(std::move(rule));
        ctx->heads.insert(predicate);
    });
    if (code && ctx && !ctx->running)
        ctx->begun = ctx->complete = false;
    return code;
}
int dlp_qx_validate(dlp_qx_context *ctx) {
    return protect([&] {
        require(ctx && ctx->begun && !ctx->running && !ctx->poisoned,
                "query context is not prepared");
        ctx->validate_plan();
    });
}
int dlp_qx_run(dlp_qx_context *ctx, dlp_qx_control control, void *user) {
    if (ctx && ctx->running)
        return protect([] { throw Failure(2, "query context is already running"); });
    int code = protect([&] {
        require(ctx && ctx->begun && !ctx->running && !ctx->poisoned,
                "query context is not prepared");
        ctx->running = true;
        ctx->complete = false;
        ctx->control = control;
        ctx->user = user;
        ctx->check(true);
        ctx->validate_plan();
        ctx->candidate.clear();
        size_t total = ctx->source_count, start = 0;
        for (const auto &relation : ctx->source) {
            auto &copy = ctx->candidate.emplace(relation.first, Relation(relation.second.arity))
                             .first->second;
            for (const auto &row : relation.second.rows) {
                ctx->check();
                for (auto id : row)
                    require(ctx->terms.count(id), "source contains undeclared term");
                copy.add(row);
            }
        }
        while (start < ctx->rules.size()) {
            size_t end = start + 1;
            while (end < ctx->rules.size() && ctx->rules[end].stratum == ctx->rules[start].stratum)
                ++end;
            bool changed = true;
            while (changed) {
                ctx->check(true);
                require(ctx->stats.rounds++ < ctx->limits.max_rounds, "max_rounds exceeded", 6);
                std::set<std::pair<ID, Row>> pending;
                for (size_t i = start; i < end; ++i) {
                    const auto &rule = ctx->rules[i];
                    for (const auto &binding : ctx->solve(rule)) {
                        ctx->check();
                        Row row;
                        for (const auto &arg : rule.head)
                            row.push_back(ctx->value(arg, binding));
                        auto relation = ctx->candidate.find(rule.predicate);
                        if (relation != ctx->candidate.end())
                            require(relation->second.arity == row.size(), "head arity mismatch", 8);
                        if (relation == ctx->candidate.end() || !relation->second.rows.count(row)) {
                            auto key = std::make_pair(rule.predicate, std::move(row));
                            if (!pending.count(key)) {
                                require(total + pending.size() < ctx->limits.max_rows,
                                        "max_rows exceeded by derived relations", 6);
                                pending.insert(std::move(key));
                            }
                        }
                    }
                }
                changed = !pending.empty();
                for (const auto &fact : pending) {
                    auto relation = ctx->candidate.find(fact.first);
                    if (relation == ctx->candidate.end())
                        relation =
                            ctx->candidate.emplace(fact.first, Relation(fact.second.size())).first;
                    relation->second.add(fact.second);
                    ++total;
                }
            }
            start = end;
        }
        ctx->check(true);
        ctx->complete = true;
    });
    if (ctx) {
        ctx->running = false;
        ctx->control = nullptr;
        ctx->user = nullptr;
        ctx->begun = false;
        if (code) {
            ctx->complete = false;
            ctx->candidate.clear();
        }
    }
    return code;
}
int dlp_qx_result(dlp_qx_context *ctx, ID predicate, size_t arity, size_t offset, ID *output,
                  size_t capacity, size_t *written, int *done) {
    if (written)
        *written = 0;
    if (done)
        *done = 1;
    return protect([&] {
        require(ctx && ctx->complete && !ctx->running && written && done && capacity &&
                    (!arity || output),
                "no complete native query result or invalid output buffer");
        require(!arity || capacity <= std::numeric_limits<size_t>::max() / arity,
                "result buffer overflow", 3);
        auto relation = ctx->candidate.find(predicate);
        if (!ctx->heads.count(predicate) || relation == ctx->candidate.end())
            return;
        require(relation->second.arity == arity, "result arity mismatch", 8);
        const auto &rows = relation->second.rows;
        if (offset >= rows.size())
            return;
        auto row = rows.begin();
        std::advance(row, offset);
        for (; row != rows.end() && *written < capacity; ++row, ++*written)
            if (arity)
                std::copy(row->begin(), row->end(), output + *written * arity);
        *done = row == rows.end();
    });
}
int dlp_qx_value(dlp_qx_context *ctx, ID id, dlp_domain_value *value) {
    return protect([&] {
        require(ctx && ctx->complete && value, "no complete native query result");
        auto term = ctx->terms.find(id);
        require(term != ctx->terms.end() && term->second.generated, "not a generated result term");
        *value = term->second.value;
    });
}
int dlp_qx_get_stats(dlp_qx_context *ctx, dlp_qx_stats *stats) {
    return protect([&] {
        require(ctx && stats, "invalid query stats arguments");
        *stats = ctx->stats;
        stats->memo_entries = ctx->memo.size();
        stats->memo_bytes = ctx->memo_bytes;
    });
}
}
