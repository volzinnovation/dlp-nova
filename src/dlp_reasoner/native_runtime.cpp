#include "native_runtime.h"
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {
using ID = uint64_t;
struct Failure : std::runtime_error {
    int code;
    Failure(int c, const std::string &m) : runtime_error(m), code(c) {}
};
thread_local char last_error[512] = {};
thread_local int last_code = 0;
void require(bool ok, const char *m) {
    if (!ok)
        throw Failure(1, m);
}
void limit(bool ok, const char *m) {
    if (!ok)
        throw Failure(2, m);
}
template <class F> int api(F f) noexcept {
    try {
        last_error[0] = 0;
        last_code = 0;
        f();
        return 0;
    } catch (const Failure &e) {
        last_code = e.code;
        std::snprintf(last_error, sizeof last_error, "%s", e.what());
    } catch (const std::bad_alloc &) {
        last_code = 3;
        std::snprintf(last_error, sizeof last_error, "native allocation failed");
    } catch (const std::exception &e) {
        last_code = 4;
        std::snprintf(last_error, sizeof last_error, "%s", e.what());
    } catch (...) {
        last_code = 4;
        std::snprintf(last_error, sizeof last_error, "unknown native failure");
    }
    return -1;
}
struct Term {
    uint32_t category = 2;
    std::string order, spelling;
    ID group = 0, symbol = 0, parent = 0;
    std::vector<ID> args;
    uint64_t depth = 0;
    bool active = false;
    std::set<ID> groups;
};
struct Expr {
    uint32_t kind = 0;
    ID ref = 0;
    std::vector<Expr> args;
};
struct Atom {
    ID predicate = 0;
    std::vector<Expr> args;
};
struct Rule {
    bool constraint = false;
    Atom head;
    std::vector<Atom> body;
    size_t variables = 0;
    std::string label;
};
struct Fact {
    ID predicate;
    std::vector<ID> args;
    bool operator<(const Fact &o) const {
        return std::tie(predicate, args) < std::tie(o.predicate, o.args);
    }
};
using Signature = std::pair<ID, std::vector<ID>>;
struct Relation {
    std::vector<const Fact *> rows;
    std::vector<std::unordered_map<ID, std::vector<const Fact *>>> columns;
};
struct State {
    ID eq, neq, top, seed, next = 1;
    dlp_runtime_limits limits;
    std::map<ID, std::string> symbols;
    std::map<ID, Term> terms;
    std::set<Fact> facts;
    std::map<ID, size_t> arities;
    std::vector<const Fact *> exported;
    std::map<Signature, ID> signatures;
    std::map<ID, ID> literals;
    std::vector<std::string> violations;
    std::set<std::string> violation_keys;
    std::atomic<bool> *cancelled = nullptr;
    dlp_runtime_stats stats{};
    bool dirty = false;
    uint64_t max_candidates = 100000000, max_matches = 10000000, max_violations = 100000;
    State(ID e, ID n, ID t, ID s, dlp_runtime_limits l)
        : eq(e), neq(n), top(t), seed(s), limits(l) {
        arities[eq] = 2;
        arities[neq] = 2;
        arities[top] = 1;
    }
    void check_cancel() {
        if (cancelled && cancelled->load(std::memory_order_relaxed))
            throw Failure(5, "native reasoning cancelled");
    }
    void violation(const std::string &m) {
        if (!violation_keys.count(m)) {
            limit(violations.size() < max_violations, "max_violations exceeded");
            violation_keys.insert(m);
            violations.push_back(m);
        }
    }
    ID find(ID id) {
        auto it = terms.find(id);
        require(it != terms.end(), "unknown term ID");
        ID root = id;
        while (terms.at(root).parent != root)
            root = terms.at(root).parent;
        while (id != root) {
            auto &t = terms.at(id);
            ID next_id = t.parent;
            t.parent = root;
            id = next_id;
        }
        return root;
    }
    bool precedes(ID a, ID b) {
        const auto &x = terms.at(a);
        const auto &y = terms.at(b);
        return std::tie(x.category, x.depth, x.order, a) <
               std::tie(y.category, y.depth, y.order, b);
    }
    bool unite(ID a, ID b) {
        a = find(a);
        b = find(b);
        if (a == b)
            return false;
        if (!precedes(a, b))
            std::swap(a, b);
        auto &x = terms.at(a);
        auto &y = terms.at(b);
        for (ID g : x.groups)
            for (ID h : y.groups)
                if (g != h)
                    violation("Equality identifies distinct datatype values (groups " +
                              std::to_string(g) + ", " + std::to_string(h) + ")");
        x.groups.insert(y.groups.begin(), y.groups.end());
        y.parent = a;
        y.groups.clear();
        ++stats.equality_merges;
        dirty = true;
        return true;
    }
    void arity(ID p, size_t n) {
        require(p != 0, "zero predicate ID");
        auto it = arities.find(p);
        require(it == arities.end() || it->second == n, "inconsistent predicate arity");
        arities[p] = n;
    }
    Fact canonical(Fact f) {
        for (ID &v : f.args)
            v = find(v);
        return f;
    }
    void store(Fact f) {
        f = canonical(std::move(f));
        if (facts.count(f))
            return;
        limit(facts.size() < limits.max_facts, "max_facts exceeded");
        facts.insert(std::move(f));
    }
    Signature signature(ID symbol, const std::vector<ID> &args) {
        std::vector<ID> v;
        v.reserve(args.size());
        for (ID x : args)
            v.push_back(find(x));
        return {symbol, std::move(v)};
    }
    void activate(ID id) {
        if ((stats.terms & 255) == 0)
            check_cancel();
        auto &t = terms.at(id);
        if (t.active)
            return;
        limit(t.depth <= limits.max_depth, "max_depth exceeded by an existential witness");
        for (ID x : t.args)
            activate(x);
        t.active = true;
        ++stats.terms;
        limit(stats.terms <= limits.max_terms, "max_terms exceeded");
        if (t.group) {
            t.groups.insert(t.group);
            auto old = literals.emplace(t.group, id);
            if (!old.second)
                unite(id, old.first->second);
        }
        if (t.symbol) {
            auto old = signatures.emplace(signature(t.symbol, t.args), id);
            if (!old.second)
                unite(id, old.first->second);
        }
        store({top, {find(id)}});
    }
    std::string witness_spelling(ID symbol, const std::vector<ID> &args) {
        std::string out = "Skolem(symbol=" + symbols.at(symbol) + ", args=(";
        for (size_t i = 0; i < args.size(); ++i) {
            if (i)
                out += ", ";
            out += terms.at(args[i]).spelling;
        }
        if (args.size() == 1)
            out += ",";
        return out + "))";
    }
    ID witness(ID symbol, std::vector<ID> args) {
        auto sig = signature(symbol, args);
        auto old = signatures.find(sig);
        if (old != signatures.end())
            return find(old->second);
        for (ID &x : args)
            x = find(x);
        uint64_t depth = 1;
        for (ID x : args)
            depth = std::max(depth, terms.at(x).depth + 1);
        limit(depth <= limits.max_depth, "max_depth exceeded by an existential witness");
        limit(terms.size() < limits.max_terms, "max_terms exceeded by a witness");
        limit(next != 0 && next < std::numeric_limits<ID>::max(), "term ID space exhausted");
        ID id = next++;
        Term t;
        t.parent = id;
        t.category = 3;
        t.symbol = symbol;
        t.args = std::move(args);
        t.depth = depth;
        t.spelling = witness_spelling(symbol, t.args);
        t.order = "Skolem:" + t.spelling;
        terms.emplace(id, std::move(t));
        signatures.emplace(std::move(sig), id);
        return id;
    }
    void congruence() {
        bool changed = true;
        while (changed) {
            changed = false;
            std::map<Signature, ID> lookup;
            for (auto &entry : terms) {
                auto &t = entry.second;
                if (!t.symbol)
                    continue;
                auto pos = lookup.emplace(signature(t.symbol, t.args), entry.first);
                if (!pos.second)
                    changed |= unite(pos.first->second, entry.first);
            }
            signatures = std::move(lookup);
        }
        std::set<Fact> normalized;
        for (const Fact &f : facts)
            normalized.insert(canonical(f));
        facts.swap(normalized);
        dirty = false;
    }
    void differences() {
        for (const Fact &f : facts)
            if (f.predicate == neq && find(f.args[0]) == find(f.args[1]))
                violation("An individual is both equal to and different from itself: " +
                          std::to_string(find(f.args[0])));
    }
    void ingest(const std::set<Fact> &input) {
        size_t count = 0;
        for (auto f : input) {
            if ((count++ & 255) == 0)
                check_cancel();
            for (ID id : f.args)
                activate(id);
            if (f.predicate == eq)
                unite(f.args[0], f.args[1]);
            store(f);
            if (f.predicate == neq) {
                std::reverse(f.args.begin(), f.args.end());
                store(std::move(f));
            }
        }
        if (dirty)
            congruence();
        differences();
    }
    bool distinct(ID a, ID b) {
        a = find(a);
        b = find(b);
        if (a == b)
            return false;
        const auto &x = terms.at(a);
        const auto &y = terms.at(b);
        return x.category == 1 && y.category == 1 && x.group && y.group && x.group != y.group;
    }
    ID bound(const Expr &e, const std::vector<ID> &binding) {
        if (e.kind == 0)
            return find(e.ref);
        if (e.kind == 1)
            return binding[e.ref];
        std::vector<ID> args;
        for (const Expr &child : e.args) {
            ID id = bound(child, binding);
            if (!id)
                return 0;
            args.push_back(id);
        }
        return witness(e.ref, std::move(args));
    }
    void constants(const Expr &e) {
        if (e.kind == 0) {
            activate(e.ref);
            return;
        }
        if (e.kind == 1)
            return;
        bool ground = true;
        for (const Expr &c : e.args) {
            constants(c);
            if (c.kind == 1)
                ground = false;
        }
        std::vector<ID> empty; // bound only after confirming recursive groundness
        auto is_ground = [](const auto &self, const Expr &x) -> bool {
            if (x.kind == 1)
                return false;
            for (const Expr &c : x.args)
                if (!self(self, c))
                    return false;
            return true;
        };
        if (ground && is_ground(is_ground, e)) {
            ID id = bound(e, empty);
            activate(id);
        }
    }
    std::map<ID, Relation> index() {
        std::map<ID, Relation> result;
        for (const Fact &f : facts) {
            auto &r = result[f.predicate];
            if (r.columns.empty())
                r.columns.resize(f.args.size());
            r.rows.push_back(&f);
            for (size_t i = 0; i < f.args.size(); ++i)
                r.columns[i][f.args[i]].push_back(&f);
        }
        return result;
    }
    void solve(const Rule &r, const std::map<ID, Relation> &idx, std::vector<size_t> remaining,
               std::vector<ID> binding, std::set<Fact> &pending) {
        if ((stats.candidate_rows & 255) == 0)
            check_cancel();
        if (remaining.empty()) {
            limit(stats.body_matches < max_matches, "max_matches exceeded");
            ++stats.body_matches;
            if (r.constraint) {
                std::string m = (r.label.empty() ? "constraint" : r.label) + " violated";
                for (size_t i = 0; i < binding.size(); ++i)
                    if (binding[i])
                        m += " slot" + std::to_string(i) + "=" + std::to_string(binding[i]);
                violation(m);
            } else {
                Fact f{r.head.predicate, {}};
                for (const Expr &e : r.head.args) {
                    ID v = bound(e, binding);
                    require(v != 0, "unsafe unbound head");
                    f.args.push_back(v);
                }
                f = canonical(std::move(f));
                if (!facts.count(f))
                    pending.insert(std::move(f));
                limit(pending.size() + facts.size() <= limits.max_facts,
                      "max_facts exceeded by candidate batch");
            }
            return;
        }
        size_t chosen = std::numeric_limits<size_t>::max(),
               best = std::numeric_limits<size_t>::max();
        std::vector<ID> values;
        const std::vector<const Fact *> *rows = nullptr;
        for (size_t position : remaining) {
            const Atom &a = r.body[position];
            std::vector<ID> v;
            for (const Expr &e : a.args)
                v.push_back(bound(e, binding));
            size_t size = 0;
            const std::vector<const Fact *> *bucket = nullptr;
            if (a.predicate == eq) {
                if (!v[0] && !v[1])
                    continue;
                size = 1;
            } else if (a.predicate == neq) {
                if (!v[0] || !v[1])
                    continue;
                size = (facts.count({neq, v}) || distinct(v[0], v[1])) ? 1 : 0;
            } else {
                auto rel = idx.find(a.predicate);
                if (rel != idx.end()) {
                    bucket = &rel->second.rows;
                    for (size_t i = 0; i < v.size(); ++i)
                        if (v[i]) {
                            auto col = rel->second.columns[i].find(v[i]);
                            if (col == rel->second.columns[i].end()) {
                                bucket = nullptr;
                                break;
                            }
                            if (col->second.size() < bucket->size())
                                bucket = &col->second;
                        }
                    size = bucket ? bucket->size() : 0;
                }
            }
            if (size < best) {
                chosen = position;
                best = size;
                values = std::move(v);
                rows = bucket;
                if (!size)
                    return;
            }
        }
        require(chosen != std::numeric_limits<size_t>::max(), "unsafe unbound equality/difference");
        const Atom &a = r.body[chosen];
        remaining.erase(std::find(remaining.begin(), remaining.end(), chosen));
        if (a.predicate == eq) {
            if (!values[0]) {
                require(a.args[0].kind == 1, "unbound equality must bind a variable");
                binding[a.args[0].ref] = values[1];
            } else if (!values[1]) {
                require(a.args[1].kind == 1, "unbound equality must bind a variable");
                binding[a.args[1].ref] = values[0];
            } else if (values[0] != values[1])
                return;
            solve(r, idx, std::move(remaining), std::move(binding), pending);
        } else if (a.predicate == neq)
            solve(r, idx, std::move(remaining), std::move(binding), pending);
        else
            for (const Fact *row : *rows) {
                if ((stats.candidate_rows & 255) == 0)
                    check_cancel();
                limit(stats.candidate_rows < max_candidates, "max_candidates exceeded");
                ++stats.candidate_rows;
                auto extended = binding;
                bool match = true;
                for (size_t i = 0; i < a.args.size(); ++i) {
                    const Expr &e = a.args[i];
                    if (e.kind == 1) {
                        ID &slot = extended[e.ref];
                        if (slot && slot != row->args[i]) {
                            match = false;
                            break;
                        }
                        slot = row->args[i];
                    } else if (values[i] != row->args[i]) {
                        match = false;
                        break;
                    }
                }
                if (match)
                    solve(r, idx, remaining, std::move(extended), pending);
            }
    }
    void run(const std::vector<Rule> &rules, const std::set<Fact> &asserted) {
        check_cancel();
        for (const auto &entry : terms)
            if (entry.second.symbol)
                signatures.emplace(signature(entry.second.symbol, entry.second.args), entry.first);
        activate(seed);
        for (const Rule &r : rules) {
            for (const Atom &a : r.body)
                for (const Expr &e : a.args)
                    constants(e);
            if (!r.constraint)
                for (const Expr &e : r.head.args)
                    constants(e);
        }
        ingest(asserted);
        if (dirty)
            congruence();
        for (;;) {
            check_cancel();
            limit(stats.rounds < limits.max_rounds, "max_rounds exceeded before a fixed point");
            ++stats.rounds;
            auto idx = index();
            std::set<Fact> pending;
            for (const Rule &r : rules) {
                std::vector<size_t> rem;
                for (size_t i = 0; i < r.body.size(); ++i)
                    rem.push_back(i);
                solve(r, idx, std::move(rem), std::vector<ID>(r.variables), pending);
            }
            if (pending.empty())
                break;
            size_t before = facts.size();
            uint64_t merges = stats.equality_merges;
            ingest(pending);
            if (facts.size() == before && merges == stats.equality_merges)
                break;
        }
        check_cancel();
        exported.reserve(facts.size());
        for (const Fact &f : facts)
            exported.push_back(&f);
        stats.facts = facts.size();
        stats.violations = violations.size();
        stats.complete = 1;
    }
};
// Structural limits are explicit IR validation constraints, not result caps.
constexpr size_t MAX_BODY = 512, MAX_EXPR_NESTING = 256;
} // namespace
struct dlp_runtime {
    State input;
    std::vector<Rule> rules;
    std::set<Fact> asserted;
    std::unique_ptr<State> result;
    std::atomic<bool> cancelled{false};
    explicit dlp_runtime(ID e, ID n, ID t, ID s, dlp_runtime_limits l) : input(e, n, t, s, l) {
        input.cancelled = &cancelled;
    }
};
namespace {
void mutable_handle(dlp_runtime *r) {
    require(r != nullptr, "null runtime");
    require(!r->result, "published runtime is immutable");
}
State &ready(dlp_runtime *r) {
    require(r && r->result, "runtime has no complete snapshot");
    return *r->result;
}
Expr copy_expr(dlp_runtime *r, const dlp_runtime_expr &e, size_t vars, size_t depth) {
    require(depth <= MAX_EXPR_NESTING, "expression nesting exceeds ABI limit 256");
    require(e.reserved == 0 && e.kind <= 2, "invalid expression kind/reserved");
    Expr out;
    out.kind = e.kind;
    out.ref = e.reference;
    if (e.kind == 0) {
        require(e.arity == 0 && r->input.terms.count(e.reference),
                "unknown constant or constant children");
    } else if (e.kind == 1) {
        require(e.arity == 0 && e.reference < vars, "invalid variable slot");
    } else {
        require(e.reference != 0 && r->input.symbols.count(e.reference),
                "undeclared Skolem symbol");
        require(!e.arity || e.arguments, "null expression children");
        for (size_t i = 0; i < e.arity; ++i)
            out.args.push_back(copy_expr(r, e.arguments[i], vars, depth + 1));
    }
    return out;
}
Atom copy_atom(dlp_runtime *r, const dlp_runtime_atom &a, size_t vars) {
    require(!a.arity || a.arguments, "null atom arguments");
    r->input.arity(a.predicate, a.arity);
    Atom out;
    out.predicate = a.predicate;
    for (size_t i = 0; i < a.arity; ++i)
        out.args.push_back(copy_expr(r, a.arguments[i], vars, 0));
    return out;
}
void variables(const Expr &e, std::set<ID> &out) {
    if (e.kind == 1)
        out.insert(e.ref);
    for (const auto &c : e.args)
        variables(c, out);
}
std::set<ID> variables(const Atom &a) {
    std::set<ID> out;
    for (const auto &e : a.args)
        variables(e, out);
    return out;
}
bool subset(const std::set<ID> &a, const std::set<ID> &b) {
    return std::includes(b.begin(), b.end(), a.begin(), a.end());
}
void safe_rule(const Rule &r, ID eq, ID neq) {
    std::set<ID> bound, needed;
    std::vector<const Atom *> equalities;
    for (const Atom &a : r.body) {
        for (const Expr &e : a.args)
            if (e.kind == 2) {
                std::set<ID> v;
                variables(e, v);
                require(v.empty(), "nonground Skolem patterns in bodies are unsupported");
            }
        auto v = variables(a);
        if (a.predicate == eq)
            equalities.push_back(&a);
        else if (a.predicate == neq)
            needed.insert(v.begin(), v.end());
        else
            bound.insert(v.begin(), v.end());
    }
    bool change = true;
    while (change) {
        size_t old = bound.size();
        for (const Atom *a : equalities) {
            std::set<ID> l, rvars;
            variables(a->args[0], l);
            variables(a->args[1], rvars);
            if (subset(l, bound))
                bound.insert(rvars.begin(), rvars.end());
            if (subset(rvars, bound))
                bound.insert(l.begin(), l.end());
        }
        change = old != bound.size();
    }
    for (const Atom *a : equalities) {
        auto v = variables(*a);
        needed.insert(v.begin(), v.end());
    }
    if (!r.constraint) {
        auto v = variables(r.head);
        needed.insert(v.begin(), v.end());
    }
    require(subset(needed, bound), "unsafe rule has unbound variables");
}
} // namespace
extern "C" {
uint32_t dlp_runtime_abi_version() { return 1; }
const char *dlp_runtime_error() { return last_error; }
int32_t dlp_runtime_error_code() { return last_code; }
int dlp_runtime_new(ID eq, ID neq, ID top, ID seed, const dlp_runtime_limits *l,
                    dlp_runtime **out) {
    if (out)
        *out = nullptr;
    return api([&] {
        require(out && l && eq && neq && top && seed, "invalid runtime arguments");
        require(eq != neq && eq != top && neq != top, "builtin predicates must differ");
        require(l->max_rounds && l->max_facts && l->max_terms, "limits must be positive");
        *out = new dlp_runtime(eq, neq, top, seed, *l);
    });
}
void dlp_runtime_free(dlp_runtime *r) { delete r; }
int dlp_runtime_cancel(dlp_runtime *r) {
    return api([&] {
        require(r, "null runtime");
        r->cancelled.store(true, std::memory_order_relaxed);
    });
}
int dlp_runtime_set_work_limits(dlp_runtime *r, ID candidates, ID matches, ID violations) {
    return api([&] {
        mutable_handle(r);
        require(candidates && matches && violations, "work limits must be positive");
        r->input.max_candidates = candidates;
        r->input.max_matches = matches;
        r->input.max_violations = violations;
    });
}
int dlp_runtime_add_symbol(dlp_runtime *r, ID symbol, const char *quoted) {
    return api([&] {
        mutable_handle(r);
        require(symbol && quoted, "invalid symbol declaration");
        require(!r->input.symbols.count(symbol), "duplicate symbol ID");
        r->input.symbols.emplace(symbol, quoted);
    });
}
int dlp_runtime_add_term(dlp_runtime *r, ID id, uint32_t category, const char *key, ID group) {
    return api([&] {
        mutable_handle(r);
        require(id && id < std::numeric_limits<ID>::max() && category <= 2 && key,
                "invalid term declaration");
        require(category == 1 || group == 0, "literal group requires literal category");
        require(!r->input.terms.count(id), "duplicate term ID");
        limit(r->input.terms.size() < r->input.limits.max_terms,
              "max_terms exceeded by dictionary");
        Term t;
        t.parent = id;
        t.category = category;
        t.order = key;
        auto separator = t.order.find(':');
        t.spelling = separator == std::string::npos ? t.order : t.order.substr(separator + 1);
        t.group = group;
        r->input.terms.emplace(id, std::move(t));
        r->input.next = std::max(r->input.next, id + 1);
    });
}
int dlp_runtime_add_skolem(dlp_runtime *r, ID id, ID symbol, const ID *args, size_t n) {
    return api([&] {
        mutable_handle(r);
        require(id && id < std::numeric_limits<ID>::max() && symbol &&
                    r->input.symbols.count(symbol) && (!n || args),
                "invalid ground Skolem declaration");
        require(!r->input.terms.count(id), "duplicate term ID");
        limit(r->input.terms.size() < r->input.limits.max_terms,
              "max_terms exceeded by dictionary");
        Term t;
        t.parent = id;
        t.category = 3;
        t.symbol = symbol;
        t.depth = 1;
        for (size_t i = 0; i < n; ++i) {
            require(r->input.terms.count(args[i]), "unknown Skolem child");
            t.args.push_back(args[i]);
            t.depth = std::max(t.depth, r->input.terms.at(args[i]).depth + 1);
        }
        limit(t.depth <= r->input.limits.max_depth, "max_depth exceeded by ground witness");
        t.spelling = r->input.witness_spelling(symbol, t.args);
        t.order = "Skolem:" + t.spelling;
        r->input.terms.emplace(id, std::move(t));
        r->input.next = std::max(r->input.next, id + 1);
    });
}
int dlp_runtime_add_fact(dlp_runtime *r, ID p, const ID *args, size_t n) {
    return api([&] {
        mutable_handle(r);
        require(!n || args, "null fact arguments");
        Fact f{p, {}};
        for (size_t i = 0; i < n; ++i) {
            require(r->input.terms.count(args[i]), "unknown fact term");
            f.args.push_back(args[i]);
        }
        r->input.arity(p, n);
        if (!r->asserted.count(f)) {
            limit(r->asserted.size() < r->input.limits.max_facts,
                  "max_facts exceeded by assertions");
            r->asserted.insert(std::move(f));
        }
    });
}
int dlp_runtime_add_rule(dlp_runtime *r, const dlp_runtime_atom *head, const dlp_runtime_atom *body,
                         size_t count, size_t vars, const char *label) {
    return api([&] {
        mutable_handle(r);
        require(count <= MAX_BODY, "rule body exceeds ABI limit 512");
        require((!count || body) && label, "invalid rule pointers");
        limit(vars <= r->input.limits.max_terms, "variable slots exceed max_terms");
        auto old_arities = r->input.arities;
        try {
            Rule rule;
            rule.constraint = !head;
            rule.variables = vars;
            rule.label = label;
            if (head)
                rule.head = copy_atom(r, *head, vars);
            for (size_t i = 0; i < count; ++i)
                rule.body.push_back(copy_atom(r, body[i], vars));
            safe_rule(rule, r->input.eq, r->input.neq);
            r->rules.push_back(std::move(rule));
        } catch (...) {
            r->input.arities = std::move(old_arities);
            throw;
        }
    });
}
int dlp_runtime_materialize(dlp_runtime *r) {
    return api([&] {
        mutable_handle(r);
        require(r->input.terms.count(r->input.seed), "undeclared nonempty-domain seed");
        auto candidate = std::make_unique<State>(r->input);
        candidate->run(r->rules, r->asserted);
        r->result = std::move(candidate);
    });
}
int dlp_runtime_get_stats(dlp_runtime *r, dlp_runtime_stats *out) {
    return api([&] {
        require(r && out, "null stats arguments");
        *out = r->result ? r->result->stats : dlp_runtime_stats{};
    });
}
int dlp_runtime_fact(dlp_runtime *r, size_t index, ID *p, ID *args, size_t cap, size_t *n) {
    return api([&] {
        auto &s = ready(r);
        require(p && n && index < s.facts.size(), "invalid fact index/output");
        const Fact &f = *s.exported[index];
        *p = f.predicate;
        *n = f.args.size();
        if (!args && cap == 0)
            return;
        require(cap >= f.args.size() && (f.args.empty() || args), "fact output capacity too small");
        std::copy(f.args.begin(), f.args.end(), args);
    });
}
int dlp_runtime_normalize(dlp_runtime *r, ID id, ID *out) {
    return api([&] {
        require(out, "null normalization output");
        *out = ready(r).find(id);
    });
}
int dlp_runtime_term(dlp_runtime *r, ID id, uint32_t *kind, ID *symbol, ID *args, size_t cap,
                     size_t *n) {
    return api([&] {
        auto &s = ready(r);
        require(kind && symbol && n, "null term output");
        id = s.find(id);
        const auto &t = s.terms.at(id);
        *kind = t.symbol ? 2 : 0;
        *symbol = t.symbol;
        *n = t.args.size();
        if (!args && cap == 0)
            return;
        require(cap >= t.args.size() && (!t.args.size() || args), "term output capacity too small");
        for (size_t i = 0; i < t.args.size(); ++i)
            args[i] = s.find(t.args[i]);
    });
}
int dlp_runtime_find_skolem(dlp_runtime *r, ID symbol, const ID *args, size_t count, ID *out) {
    return api([&] {
        auto &s = ready(r);
        require(symbol && out && (!count || args), "invalid witness lookup arguments");
        std::vector<ID> children;
        for (size_t i = 0; i < count; ++i)
            children.push_back(s.find(args[i]));
        auto found = s.signatures.find({symbol, children});
        *out = found == s.signatures.end() ? 0 : s.find(found->second);
    });
}
int dlp_runtime_violation(dlp_runtime *r, size_t index, const char **out) {
    return api([&] {
        auto &s = ready(r);
        require(out && index < s.violations.size(), "invalid violation index/output");
        *out = s.violations[index].c_str();
    });
}
}
