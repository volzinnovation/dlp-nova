#include "native_package.h"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace {
constexpr size_t MAX_BYTES = 64 * 1024 * 1024, MAX_TEXT = 1024 * 1024, MAX_RECORDS = 2000000,
                 MAX_RULES = 100000;
const char MAGIC[8] = {'D', 'L', 'P', 'N', 'P', 'K', 'G', '1'};
thread_local char error_text[512] = {};
thread_local int error_code = 0;
struct Failure : std::runtime_error {
    int code;
    Failure(int c, const std::string &m) : runtime_error(m), code(c) {}
};
void check(bool ok, const char *m, int code = 1) {
    if (!ok)
        throw Failure(code, m);
}
void query_core(int result) {
    if (result) {
        int code = dlp_qx_last_status();
        throw Failure(code == 6 ? 3 : code == 9 ? 6 : 4, dlp_qx_last_error());
    }
}
void core(int result) {
    if (result) {
        int code = dlp_runtime_error_code();
        throw Failure(code == 2 || code == 3 ? 3 : code == 5 ? 6 : 4, dlp_runtime_error());
    }
}
template <class F> int api(F action) noexcept {
    error_code = 0;
    error_text[0] = 0;
    try {
        action();
        return 0;
    } catch (const Failure &e) {
        error_code = e.code;
        std::snprintf(error_text, sizeof error_text, "%s", e.what());
    } catch (const std::bad_alloc &) {
        error_code = 3;
        std::strcpy(error_text, "native package allocation failed");
    } catch (const std::exception &e) {
        error_code = 5;
        std::snprintf(error_text, sizeof error_text, "%s", e.what());
    } catch (...) {
        error_code = 5;
        std::strcpy(error_text, "unknown native package failure");
    }
    return -1;
}
uint32_t rotate(uint32_t value, unsigned n) { return (value >> n) | (value << (32 - n)); }
std::array<uint8_t, 32> sha256(const uint8_t *bytes, size_t size) {
    static constexpr uint32_t constants[64] = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2};
    std::array<uint32_t, 8> state{{0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f,
                                   0x9b05688c, 0x1f83d9ab, 0x5be0cd19}};
    const size_t blocks = (size + 9 + 63) / 64;
    for (size_t block = 0; block < blocks; ++block) {
        uint32_t words[64]{};
        for (size_t i = 0; i < 64; ++i) {
            const size_t offset = block * 64 + i;
            uint8_t byte = 0;
            if (offset < size)
                byte = bytes[offset];
            else if (offset == size)
                byte = 0x80;
            else if (offset >= blocks * 64 - 8)
                byte = static_cast<uint8_t>((static_cast<uint64_t>(size) * 8) >>
                                            ((blocks * 64 - 1 - offset) * 8));
            words[i / 4] |= static_cast<uint32_t>(byte) << (24 - (i % 4) * 8);
        }
        for (size_t i = 16; i < 64; ++i) {
            auto a = words[i - 15], b = words[i - 2];
            words[i] = words[i - 16] + (rotate(a, 7) ^ rotate(a, 18) ^ (a >> 3)) + words[i - 7] +
                       (rotate(b, 17) ^ rotate(b, 19) ^ (b >> 10));
        }
        uint32_t a = state[0], b = state[1], c = state[2], d = state[3], e = state[4], f = state[5],
                 g = state[6], h = state[7];
        for (size_t i = 0; i < 64; ++i) {
            const uint32_t first = h + (rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25)) +
                                   ((e & f) ^ (~e & g)) + constants[i] + words[i];
            const uint32_t second =
                (rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
            h = g;
            g = f;
            f = e;
            e = d + first;
            d = c;
            c = b;
            b = a;
            a = first + second;
        }
        state[0] += a;
        state[1] += b;
        state[2] += c;
        state[3] += d;
        state[4] += e;
        state[5] += f;
        state[6] += g;
        state[7] += h;
    }
    std::array<uint8_t, 32> result{};
    for (size_t i = 0; i < 32; ++i)
        result[i] = static_cast<uint8_t>(state[i / 4] >> (24 - (i % 4) * 8));
    return result;
}
bool utf8(const std::string &s) {
    for (size_t i = 0; i < s.size();) {
        uint32_t code = static_cast<unsigned char>(s[i++]);
        if (code < 128)
            continue;
        unsigned more = code >= 0xc2 && code <= 0xdf   ? 1
                        : code >= 0xe0 && code <= 0xef ? 2
                        : code >= 0xf0 && code <= 0xf4 ? 3
                                                       : 0;
        if (!more || more > s.size() - i)
            return false;
        const unsigned count = more;
        code &= (1u << (6 - more)) - 1;
        while (more--) {
            uint32_t byte = static_cast<unsigned char>(s[i++]);
            if ((byte & 0xc0) != 0x80)
                return false;
            code = (code << 6) | (byte & 0x3f);
        }
        if ((count == 1 && code < 0x80) || (count == 2 && code < 0x800) ||
            (count == 3 && code < 0x10000) || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff))
            return false;
    }
    return true;
}
struct Reader {
    const uint8_t *data;
    size_t size, offset = 0;
    size_t remaining() const { return size - offset; }
    uint64_t number(size_t width) {
        check(width <= remaining(), "truncated native package field");
        uint64_t out = 0;
        for (size_t i = 0; i < width; ++i)
            out |= static_cast<uint64_t>(data[offset++]) << (8 * i);
        return out;
    }
    std::string text(bool nul = false) {
        uint64_t n = number(4);
        check(n <= MAX_TEXT && n <= remaining(), "invalid native package text length",
              n > MAX_TEXT ? 3 : 1);
        std::string out(reinterpret_cast<const char *>(data + offset), static_cast<size_t>(n));
        offset += n;
        check(utf8(out) && (nul || out.find('\0') == std::string::npos),
              "invalid native package UTF-8 text");
        return out;
    }
    Reader section(size_t n) {
        check(n <= remaining(), "truncated native package record");
        Reader out{data + offset, n};
        offset += n;
        return out;
    }
    void end() { check(!remaining(), "trailing native package record data"); }
};
bool iri(const std::string &value) {
    if (value.find(':') == std::string::npos || value.empty())
        return false;
    for (unsigned char c : value)
        if (c <= 32 || c == 127)
            return false;
    return true;
}
struct Term {
    uint64_t id = 0, symbol = 0;
    uint32_t kind = 0;
    std::string lexical, datatype, language;
    bool has_datatype = false, has_language = false;
    std::vector<uint64_t> args;
};
Term term(Reader &r) {
    Term t;
    t.kind = static_cast<uint32_t>(r.number(1));
    check(t.kind >= 1 && t.kind <= 6, "invalid dictionary term tag");
    t.lexical = r.text(true);
    if (t.kind == 1)
        check(iri(t.lexical), "invalid dictionary IRI");
    if (t.kind == 2)
        check(!t.lexical.empty(), "empty blank node identifier");
    if (t.kind == 5) {
        check(!t.lexical.empty(), "empty integer");
        size_t pos = t.lexical[0] == '-' ? 1 : 0;
        check(pos < t.lexical.size(), "invalid integer term");
        check(t.lexical[pos] != '0' || pos + 1 == t.lexical.size(), "noncanonical integer term");
        check(t.lexical != "-0", "noncanonical integer term");
        for (; pos < t.lexical.size(); ++pos)
            check(t.lexical[pos] >= '0' && t.lexical[pos] <= '9', "invalid integer term");
    }
    if (t.kind == 6)
        check(t.lexical == "dlp-internal-nonempty-domain", "invalid domain seed");
    if (t.kind == 3) {
        auto flags = r.number(1);
        check(flags <= 2, "invalid literal flags");
        t.has_datatype = flags == 1;
        t.has_language = flags == 2;
        if (t.has_datatype) {
            t.datatype = r.text();
            check(iri(t.datatype), "invalid datatype IRI");
        }
        if (t.has_language) {
            t.language = r.text();
            check(!t.language.empty(), "empty literal language");
            for (unsigned char c : t.language)
                check((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') ||
                          c == '-',
                      "invalid literal language");
        }
    }
    return t;
}
struct Expr {
    dlp_runtime_expr value{};
    std::vector<Expr> children;
    std::vector<dlp_runtime_expr> arguments;
    void bind() {
        for (auto &c : children)
            c.bind();
        arguments.clear();
        for (const auto &c : children)
            arguments.push_back(c.value);
        value.arguments = arguments.data();
        value.arity = arguments.size();
    }
};
Expr expression(Reader &r, size_t depth) {
    check(depth <= 256, "native expression nesting exceeds256", 3);
    Expr e;
    e.value.kind = static_cast<uint32_t>(r.number(1));
    e.value.reference = r.number(8);
    check(e.value.kind <= 2, "invalid expression tag");
    const auto n = r.number(4);
    check(e.value.kind == 2 || n == 0, "scalar expression has children");
    check(n <= r.remaining() / 13, "invalid expression child count");
    for (uint64_t i = 0; i < n; ++i)
        e.children.push_back(expression(r, depth + 1));
    return e;
}
struct Atom {
    dlp_runtime_atom value{};
    std::vector<Expr> expressions;
    std::vector<dlp_runtime_expr> arguments;
    void bind() {
        for (auto &e : expressions)
            e.bind();
        for (const auto &e : expressions)
            arguments.push_back(e.value);
        value.arguments = arguments.data();
        value.arity = arguments.size();
    }
};
Atom atom(Reader &r) {
    Atom a;
    a.value.predicate = r.number(8);
    const auto n = r.number(4);
    check(n <= r.remaining() / 13, "invalid atom arity");
    for (uint64_t i = 0; i < n; ++i)
        a.expressions.push_back(expression(r, 0));
    return a;
}
using Identity = std::tuple<uint32_t, std::string, bool, std::string, bool, std::string>;
Identity identity(const Term &t) {
    auto language = t.language;
    for (char &c : language)
        if (c >= 'A' && c <= 'Z')
            c = static_cast<char>(c - 'A' + 'a');
    return {t.kind, t.lexical, t.has_datatype, t.datatype, t.has_language, language};
}
struct QueryMetadata {
    dlp_domain_value value{};
    int32_t status = 1;
    uint32_t canonical = 0, group = 0, roles = 0;
    uint64_t key = 0;
    std::string order, canonical_order;
};
struct QueryNode {
    dlp_qx_node value{};
    std::vector<dlp_qx_arg> args;
    std::vector<int32_t> groups;
    void bind() {
        value.args = args.data();
        value.arity = args.size();
        value.groups = groups.data();
        value.group_count = groups.size();
    }
};
struct QueryRule {
    uint64_t stratum = 0, predicate = 0;
    std::vector<dlp_qx_arg> head;
    std::vector<std::string> slots;
    std::vector<bool> given;
    std::vector<QueryNode> body;
};
dlp_qx_arg query_arg(Reader &r) {
    dlp_qx_arg out;
    out.slot = static_cast<int32_t>(r.number(4));
    out.constant = r.number(8);
    return out;
}
dlp_domain_value domain_value(Reader &r) {
    dlp_domain_value out{};
    out.tag = static_cast<uint32_t>(r.number(4));
    out.reserved = static_cast<uint32_t>(r.number(4));
    out.a = static_cast<int64_t>(r.number(8));
    out.b = static_cast<int64_t>(r.number(8));
    out.c = static_cast<int64_t>(r.number(8));
    uint64_t x = r.number(8), y = r.number(8);
    static_assert(sizeof(double) == 8, "binary64 required");
    std::memcpy(&out.x, &x, 8);
    std::memcpy(&out.y, &y, 8);
    return out;
}
void view(const Term &t, dlp_package_term_view *out) {
    *out = {};
    out->id = t.id;
    out->kind = t.kind;
    out->lexical = t.lexical.data();
    out->lexical_size = t.lexical.size();
    if (t.has_datatype) {
        out->datatype = t.datatype.data();
        out->datatype_size = t.datatype.size();
    }
    if (t.has_language) {
        out->language = t.language.data();
        out->language_size = t.language.size();
    }
    out->symbol = t.symbol;
    out->arguments = t.args.data();
    out->arity = t.args.size();
}
} // namespace
struct dlp_native_package {
    dlp_runtime *runtime = nullptr;
    std::string profile, context;
    std::vector<Term> terms, predicates;
    std::map<uint64_t, std::string> symbols;
    std::vector<QueryRule> queries;
    std::map<uint64_t, QueryMetadata> metadata;
    uint64_t rdf_type = 0;
    std::map<uint64_t, uint64_t> classes;
    std::map<uint64_t, size_t> horn_arities;
    ~dlp_native_package() { dlp_runtime_free(runtime); }
};
namespace {
void validate_queries(dlp_native_package *package, const dlp_native_package_options *options,
                      uint64_t seed) {
    if (package->queries.empty())
        return;
    check(package->metadata.size() == package->terms.size(), "missing required query term metadata",
          2);
    dlp_qx_limits limits{options->reasoning.max_facts, options->max_matches,
                         options->reasoning.max_rounds, options->reasoning.max_terms,
                         options->max_candidates};
    dlp_qx_context *raw = nullptr;
    query_core(dlp_qx_new(&limits, &raw));
    std::unique_ptr<dlp_qx_context, void (*)(dlp_qx_context *)> context(raw, dlp_qx_free);
    query_core(dlp_qx_begin(raw));
    for (const auto &t : package->terms) {
        const auto &m = package->metadata.at(t.id);
        query_core(dlp_qx_term(raw, t.id, &m.value, m.status, m.canonical, m.group, m.key));
        query_core(dlp_qx_term_roles(raw, t.id, m.roles));
        query_core(dlp_qx_term_order(raw, t.id, m.order.data(), m.order.size(),
                                     m.canonical_order.data(), m.canonical_order.size()));
    }
    auto check_arity = [&](uint64_t predicate, size_t arity) {
        auto found = package->horn_arities.find(predicate);
        check(found == package->horn_arities.end() || found->second == arity,
              "query arity conflicts with Horn predicate", 4);
        if (predicate == package->rdf_type)
            check(arity == 2, "rdf:type query arity must be two", 4);
    };
    for (const auto &r : package->queries) {
        check_arity(r.predicate, r.head.size());
        for (const auto &node : r.body)
            if (node.value.kind <= 2 || node.value.kind == 5)
                check_arity(node.value.predicate, node.args.size());
        std::vector<uint64_t> initial(r.slots.size());
        for (size_t i = 0; i < initial.size(); ++i)
            if (r.given[i])
                initial[i] = seed;
        auto nodes = r.body;
        std::vector<dlp_qx_node> body;
        for (auto &n : nodes) {
            n.bind();
            body.push_back(n.value);
        }
        query_core(dlp_qx_rule(raw, r.stratum, r.predicate, r.head.size(), r.head.data(),
                               initial.size(), initial.data(), body.data(), body.size()));
    }
    query_core(dlp_qx_validate(raw));
}
} // namespace
extern "C" {
uint32_t dlp_native_package_abi_version() { return 1; }
const char *dlp_native_package_error() { return error_text; }
int32_t dlp_native_package_error_code() { return error_code; }
int dlp_native_package_load(const uint8_t *bytes, size_t size,
                            const dlp_native_package_options *options, dlp_native_package **out) {
    if (out)
        *out = nullptr;
    return api([&] {
        check(out && options && bytes && size >= 48, "invalid native package buffers/options");
        check(size - 48 <= MAX_BYTES, "native package exceeds64MiB", 3);
        check(std::memcmp(bytes, MAGIC, 8) == 0, "unsupported native package magic", 2);
        Reader header{bytes + 8, 8};
        const uint64_t length = header.number(8);
        check(length == size - 48, "native package length mismatch");
        const auto checksum = sha256(bytes + 48, size - 48);
        check(std::memcmp(checksum.data(), bytes + 16, 32) == 0,
              "native package checksum mismatch");
        Reader reader{bytes + 48, size - 48};
        check(reader.number(4) == 1, "unsupported native package version", 2);
        check(reader.text() == "dlp-domains-v1", "unsupported native domain semantic profile", 2);
        auto package = std::make_unique<dlp_native_package>();
        package->profile = reader.text();
        check(package->profile == "L0" || package->profile == "L1" || package->profile == "L2" ||
                  package->profile == "L3",
              "unsupported Horn profile", 2);
        package->context = reader.text(true);
        const uint64_t eq = reader.number(8), neq = reader.number(8), top = reader.number(8),
                       seed = reader.number(8);
        core(dlp_runtime_new(eq, neq, top, seed, &options->reasoning, &package->runtime));
        package->horn_arities = {{eq, 2}, {neq, 2}, {top, 1}};
        core(dlp_runtime_set_work_limits(package->runtime, options->max_candidates,
                                         options->max_matches, options->max_violations));
        std::set<uint64_t> predicates;
        std::set<Identity> term_identities, predicate_identities;
        std::set<std::string> symbol_names;
        std::map<uint64_t, uint32_t> kinds;
        size_t records = 0, rules = 0;
        bool ended = false;
        while (reader.remaining()) {
            check(++records <= MAX_RECORDS, "native record limit exceeded", 3);
            const auto opcode = reader.number(1), length = reader.number(8);
            check(length <= reader.remaining(), "truncated native package record");
            Reader record = reader.section(static_cast<size_t>(length));
            if (opcode == 0) {
                check(!ended, "duplicate native end record");
                ended = true;
                record.end();
                reader.end();
                break;
            }
            if (opcode == 1) {
                const uint64_t id = record.number(8);
                auto quoted = record.text(), name = record.text(true);
                check(id && !package->symbols.count(id) && symbol_names.insert(name).second,
                      "duplicate or zero symbol ID/name");
                core(dlp_runtime_add_symbol(package->runtime, id, quoted.c_str()));
                package->symbols.emplace(id, std::move(name));
            } else if (opcode == 2) {
                const uint64_t id = record.number(8);
                const uint32_t category = static_cast<uint32_t>(record.number(4));
                const uint64_t group = record.number(8);
                auto order = record.text();
                auto value = term(record);
                value.id = id;
                check((value.kind == 1 && category == 0) || (value.kind == 3 && category == 1) ||
                          ((value.kind == 2 || value.kind == 4 || value.kind == 5 ||
                            value.kind == 6) &&
                           category == 2),
                      "term category disagrees with dictionary tag");
                check(!kinds.count(id) && term_identities.insert(identity(value)).second,
                      "duplicate term ID/value");
                core(dlp_runtime_add_term(package->runtime, id, category, order.c_str(), group));
                kinds.emplace(id, value.kind);
                package->terms.push_back(std::move(value));
            } else if (opcode == 3) {
                Term value;
                value.kind = 7;
                value.id = record.number(8);
                value.symbol = record.number(8);
                const auto arity = record.number(4);
                check(arity <= record.remaining() / 8, "invalid ground witness arity");
                for (uint64_t i = 0; i < arity; ++i)
                    value.args.push_back(record.number(8));
                check(!kinds.count(value.id), "duplicate witness ID");
                core(dlp_runtime_add_skolem(package->runtime, value.id, value.symbol,
                                            value.args.data(), value.args.size()));
                kinds.emplace(value.id, 7);
                package->terms.push_back(std::move(value));
            } else if (opcode == 4) {
                const uint64_t predicate = record.number(8), arity = record.number(4);
                check(predicates.count(predicate), "undeclared fact predicate");
                package->horn_arities.emplace(predicate, arity);
                check(arity <= record.remaining() / 8, "invalid fact arity");
                std::vector<uint64_t> args;
                for (uint64_t i = 0; i < arity; ++i)
                    args.push_back(record.number(8));
                core(dlp_runtime_add_fact(package->runtime, predicate, args.data(), args.size()));
            } else if (opcode == 5) {
                check(++rules <= MAX_RULES, "native rule limit exceeded", 3);
                const auto has_head = record.number(1), variables = record.number(4);
                check(has_head <= 1, "invalid constraint/head flag");
                check(variables <= options->reasoning.max_terms &&
                          variables <= record.remaining() / 4,
                      "variable name table exceeds bounds", 3);
                std::set<std::string> variable_names;
                for (uint64_t i = 0; i < variables; ++i)
                    check(variable_names.insert(record.text()).second, "duplicate variable name");
                auto label = record.text();
                Atom head;
                if (has_head)
                    head = atom(record);
                const auto count = record.number(4);
                check(count <= 512 && count <= record.remaining() / 12,
                      "native rule body bound exceeded", 3);
                std::vector<Atom> body;
                for (uint64_t i = 0; i < count; ++i)
                    body.push_back(atom(record));
                std::vector<dlp_runtime_atom> flat;
                if (has_head) {
                    check(predicates.count(head.value.predicate), "undeclared head predicate");
                    package->horn_arities.emplace(head.value.predicate, head.expressions.size());
                    head.bind();
                }
                for (auto &a : body) {
                    check(predicates.count(a.value.predicate), "undeclared body predicate");
                    package->horn_arities.emplace(a.value.predicate, a.expressions.size());
                    a.bind();
                    flat.push_back(a.value);
                }
                core(dlp_runtime_add_rule(package->runtime, has_head ? &head.value : nullptr,
                                          flat.data(), flat.size(), static_cast<size_t>(variables),
                                          label.c_str()));
            } else if (opcode == 6) {
                const uint64_t id = record.number(8);
                auto value = term(record);
                check(value.kind == 1 || value.kind == 4, "invalid predicate term type");
                check(id && predicates.insert(id).second &&
                          predicate_identities.insert(identity(value)).second,
                      "duplicate or zero predicate ID/value");
                value.id = id;
                package->predicates.push_back(std::move(value));
            } else if (opcode == 10) {
                check(package->queries.size() < MAX_RULES, "native query rule limit exceeded", 3);
                QueryRule rule;
                rule.stratum = record.number(8);
                rule.predicate = record.number(8);
                check(predicates.count(rule.predicate), "undeclared query head predicate");
                auto n = record.number(4);
                check(n <= 4096 && n <= record.remaining() / 12, "query head arity exceeds bounds",
                      3);
                for (uint64_t i = 0; i < n; ++i)
                    rule.head.push_back(query_arg(record));
                n = record.number(4);
                check(n <= 4096 && n <= record.remaining() / 5, "query slot table exceeds bounds",
                      3);
                std::set<std::string> names;
                for (uint64_t i = 0; i < n; ++i) {
                    auto name = record.text();
                    check(names.insert(name).second, "duplicate query slot name");
                    rule.slots.push_back(name);
                    auto given = record.number(1);
                    check(given <= 1, "invalid given flag");
                    rule.given.push_back(given != 0);
                }
                n = record.number(4);
                check(n <= 10000, "query body bound exceeded", 3);
                for (uint64_t i = 0; i < n; ++i) {
                    QueryNode node;
                    node.value.kind = static_cast<uint32_t>(record.number(4));
                    node.value.opcode = static_cast<uint32_t>(record.number(4));
                    node.value.predicate = record.number(8);
                    check(node.value.kind <= 5, "unsupported query/provider node", 2);
                    auto arity = record.number(4);
                    check(arity <= 4096 && arity <= record.remaining() / 12,
                          "query node arity exceeds bounds", 3);
                    for (uint64_t j = 0; j < arity; ++j)
                        node.args.push_back(query_arg(record));
                    node.value.output = query_arg(record);
                    auto groups = record.number(4);
                    check(groups <= 4096 && groups <= record.remaining() / 4,
                          "query group bound exceeded", 3);
                    for (uint64_t j = 0; j < groups; ++j)
                        node.groups.push_back(static_cast<int32_t>(record.number(4)));
                    node.value.value_slot = static_cast<int32_t>(record.number(4));
                    if (node.value.kind <= 2 || node.value.kind == 5)
                        check(predicates.count(node.value.predicate),
                              "undeclared query source predicate");
                    rule.body.push_back(std::move(node));
                }
                package->queries.push_back(std::move(rule));
            } else if (opcode == 11) {
                const auto id = record.number(8);
                check(kinds.count(id) && !package->metadata.count(id),
                      "undeclared/duplicate query term metadata");
                QueryMetadata meta;
                meta.status = static_cast<int32_t>(record.number(4));
                meta.canonical = static_cast<uint32_t>(record.number(1));
                meta.group = static_cast<uint32_t>(record.number(4));
                meta.key = record.number(8);
                check(meta.status >= 0 && meta.status <= 8 && meta.canonical <= 1 &&
                          meta.group <= 4,
                      "invalid query term metadata");
                if (!meta.status)
                    meta.value = domain_value(record);
                meta.order = record.text(true);
                meta.canonical_order = record.text(true);
                meta.roles = static_cast<uint32_t>(record.number(4));
                check(meta.roles <= 15, "invalid query role flags");
                check(meta.order.size() <= 32768 && meta.canonical_order.size() <= 32768,
                      "query term order key exceeds bound", 3);
                package->metadata.emplace(id, std::move(meta));
            } else if (opcode == 12) {
                check(!package->rdf_type, "duplicate RDF type expansion map");
                package->rdf_type = record.number(8);
                check(predicates.count(package->rdf_type), "undeclared RDF type predicate");
                auto count = record.number(4);
                check(count <= record.remaining() / 16, "truncated RDF class expansion map");
                for (uint64_t i = 0; i < count; ++i) {
                    const auto predicate = record.number(8), term = record.number(8);
                    check(predicates.count(predicate) && kinds.count(term) &&
                              package->classes.emplace(predicate, term).second,
                          "invalid RDF class expansion map");
                }
            } else
                throw Failure(2, "unsupported required native package record");
            record.end();
        }
        check(ended, "missing native package end record");
        check(predicates.count(eq) && predicates.count(neq) && predicates.count(top),
              "missing builtin predicate dictionary entries");
        check(kinds.count(seed) && kinds.at(seed) == 6, "invalid native seed dictionary entry");
        auto builtin = [&](uint64_t id, const char *name) {
            for (const auto &p : package->predicates)
                if (p.id == id)
                    return p.kind == 4 && p.lexical == name;
            return false;
        };
        check(builtin(eq, "urn:dlp:internal:eq") && builtin(neq, "urn:dlp:internal:neq") &&
                  builtin(top, "urn:dlp:internal:top"),
              "incorrect builtin predicate metadata");
        if (package->rdf_type) {
            auto find_term = [](const std::vector<Term> &table, uint64_t id) -> const Term & {
                for (const auto &t : table)
                    if (t.id == id)
                        return t;
                throw Failure(1, "missing dictionary entry");
            };
            const auto &type = find_term(package->predicates, package->rdf_type);
            check(type.kind == 1 &&
                      type.lexical == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
                  "invalid RDF type expansion predicate");
            for (const auto &pair : package->classes) {
                const auto &predicate = find_term(package->predicates, pair.first);
                const auto &value = find_term(package->terms, pair.second);
                check(predicate.kind == 1 && value.kind == 1 && predicate.lexical == value.lexical,
                      "RDF class expansion identity mismatch");
            }
        }
        validate_queries(package.get(), options, seed);
        core(dlp_runtime_materialize(package->runtime));
        *out = package.release();
    });
}
void dlp_native_package_free(dlp_native_package *p) { delete p; }
int dlp_native_package_runtime(dlp_native_package *p, dlp_runtime **out) {
    return api([&] {
        check(p && p->runtime && out, "package has no runtime");
        *out = p->runtime;
    });
}
int dlp_native_package_take_runtime(dlp_native_package *p, dlp_runtime **out) {
    return api([&] {
        check(p && p->runtime && out, "package has no runtime");
        *out = p->runtime;
        p->runtime = nullptr;
    });
}
const char *dlp_native_package_profile(dlp_native_package *p) {
    return p ? p->profile.c_str() : nullptr;
}
int dlp_native_package_context(dlp_native_package *p, const uint8_t **bytes, size_t *size) {
    return api([&] {
        check(p && bytes && size, "invalid context output");
        *bytes = reinterpret_cast<const uint8_t *>(p->context.data());
        *size = p->context.size();
    });
}
int dlp_native_package_counts(dlp_native_package *p, size_t *terms, size_t *predicates,
                              size_t *symbols) {
    return api([&] {
        check(p && terms && predicates && symbols, "invalid dictionary counts output");
        *terms = p->terms.size();
        *predicates = p->predicates.size();
        *symbols = p->symbols.size();
    });
}
int dlp_native_package_term(dlp_native_package *p, size_t index, dlp_package_term_view *out) {
    return api([&] {
        check(p && out && index < p->terms.size(), "invalid term dictionary index");
        view(p->terms[index], out);
    });
}
int dlp_native_package_predicate(dlp_native_package *p, size_t index, dlp_package_term_view *out) {
    return api([&] {
        check(p && out && index < p->predicates.size(), "invalid predicate dictionary index");
        view(p->predicates[index], out);
    });
}
int dlp_native_package_symbol(dlp_native_package *p, size_t index, uint64_t *id, const char **name,
                              size_t *size) {
    return api([&] {
        check(p && id && name && size && index < p->symbols.size(),
              "invalid symbol dictionary index");
        auto it = p->symbols.begin();
        std::advance(it, index);
        *id = it->first;
        *name = it->second.data();
        *size = it->second.size();
    });
}
}

namespace {
uint64_t term_ceiling(dlp_native_package *p) {
    check(p && p->runtime, "package runtime is unavailable");
    uint64_t maximum = 0;
    for (const auto &t : p->terms)
        maximum = std::max(maximum, t.id);
    dlp_runtime_stats stats{};
    core(dlp_runtime_get_stats(p->runtime, &stats));
    for (size_t i = 0; i < stats.facts; ++i) {
        uint64_t predicate = 0;
        size_t count = 0;
        core(dlp_runtime_fact(p->runtime, i, &predicate, nullptr, 0, &count));
        std::vector<uint64_t> args(count);
        core(dlp_runtime_fact(p->runtime, i, &predicate, args.data(), args.size(), &count));
        for (uint64_t id : args)
            maximum = std::max(maximum, id);
    }
    check(maximum < std::numeric_limits<uint64_t>::max(), "term ID space exhausted", 3);
    return maximum + 1;
}
} // namespace
extern "C" int dlp_native_package_next_term_id(dlp_native_package *p, uint64_t *out) {
    return api([&] {
        check(out, "null next term output");
        *out = term_ceiling(p);
    });
}
extern "C" int dlp_native_package_prepare_query(dlp_native_package *p, const dlp_qx_limits *limits,
                                                const dlp_package_parameter *parameters,
                                                size_t count, dlp_qx_context **out) {
    if (out)
        *out = nullptr;
    return api([&] {
        check(p && p->runtime && limits && out && (!count || parameters),
              "invalid query preparation arguments");
        check(!p->queries.empty(), "package has no local query plan", 2);
        check(count <= 4096, "query parameter bound exceeded", 3);
        dlp_runtime_stats source_stats{};
        core(dlp_runtime_get_stats(p->runtime, &source_stats));
        check(source_stats.complete && !source_stats.violations,
              "query requires a complete consistent Horn snapshot", 4);
        std::unique_ptr<dlp_qx_context, void (*)(dlp_qx_context *)> context(nullptr, dlp_qx_free);
        dlp_qx_context *created = nullptr;
        query_core(dlp_qx_new(limits, &created));
        context.reset(created);
        query_core(dlp_qx_begin(created));
        std::set<uint64_t> registered;
        auto register_term = [&](uint64_t id, const QueryMetadata &meta) {
            if (!registered.insert(id).second)
                return;
            query_core(dlp_qx_term(created, id, &meta.value, meta.status, meta.canonical,
                                   meta.group, meta.key));
            query_core(dlp_qx_term_order(created, id, meta.order.data(), meta.order.size(),
                                         meta.canonical_order.data(), meta.canonical_order.size()));
            query_core(dlp_qx_term_roles(created, id, meta.roles));
        };
        for (const auto &t : p->terms) {
            auto m = p->metadata.find(t.id);
            register_term(t.id, m == p->metadata.end() ? QueryMetadata{} : m->second);
        }
        dlp_runtime_stats stats{};
        core(dlp_runtime_get_stats(p->runtime, &stats));
        for (size_t i = 0; i < stats.facts; ++i) {
            uint64_t predicate = 0;
            size_t arity = 0;
            core(dlp_runtime_fact(p->runtime, i, &predicate, nullptr, 0, &arity));
            std::vector<uint64_t> row(arity);
            core(dlp_runtime_fact(p->runtime, i, &predicate, row.data(), row.size(), &arity));
            for (auto id : row)
                register_term(id, QueryMetadata{});
            query_core(dlp_qx_rows(created, predicate, arity, row.data(), 1, 1));
            auto cls = p->classes.find(predicate);
            if (arity == 1 && p->rdf_type && cls != p->classes.end()) {
                uint64_t class_term = 0;
                core(dlp_runtime_normalize(p->runtime, cls->second, &class_term));
                uint64_t typed[2] = {row[0], class_term};
                query_core(dlp_qx_rows(created, p->rdf_type, 2, typed, 1, 1));
            }
        }
        std::map<std::string, uint64_t> bindings;
        const uint64_t fresh = term_ceiling(p);
        for (size_t i = 0; i < count; ++i) {
            const auto &parameter = parameters[i];
            check(parameter.name && parameter.id, "invalid query parameter");
            std::string name(parameter.name);
            check(name.size() <= MAX_TEXT && utf8(name) &&
                      bindings.emplace(name, parameter.id).second,
                  "duplicate/invalid query parameter name");
            if (!registered.count(parameter.id)) {
                check(parameter.id >= fresh, "parameter ID collides with source dictionary");
                check(parameter.identity_order_size <= 32768 &&
                          parameter.canonical_order_size <= 32768 &&
                          (!parameter.identity_order_size || parameter.identity_order) &&
                          (!parameter.canonical_order_size || parameter.canonical_order),
                      "invalid parameter identity key");
                QueryMetadata meta;
                meta.value = parameter.value;
                meta.status = parameter.decode_status;
                meta.canonical = parameter.canonical;
                meta.group = parameter.neq_group;
                meta.key = parameter.neq_key;
                meta.roles = parameter.roles;
                if (parameter.identity_order_size)
                    meta.order.assign(parameter.identity_order, parameter.identity_order_size);
                if (parameter.canonical_order_size)
                    meta.canonical_order.assign(parameter.canonical_order,
                                                parameter.canonical_order_size);
                register_term(parameter.id, meta);
            }
        }
        auto canonical = [&](dlp_qx_arg a) {
            if (a.slot < 0) {
                uint64_t normalized = 0;
                core(dlp_runtime_normalize(p->runtime, a.constant, &normalized));
                a.constant = normalized;
            }
            return a;
        };
        for (const auto &rule : p->queries) {
            std::vector<dlp_qx_arg> head;
            for (auto a : rule.head)
                head.push_back(canonical(a));
            std::vector<uint64_t> initial(rule.slots.size());
            for (size_t i = 0; i < rule.slots.size(); ++i) {
                auto binding = bindings.find(rule.slots[i]);
                check(binding != bindings.end() || !rule.given[i],
                      "missing required query parameter");
                if (binding != bindings.end()) {
                    initial[i] = binding->second;
                    if (initial[i] < fresh) {
                        uint64_t normalized = 0;
                        core(dlp_runtime_normalize(p->runtime, initial[i], &normalized));
                        initial[i] = normalized;
                    }
                }
            }
            std::vector<QueryNode> nodes = rule.body;
            std::vector<dlp_qx_node> flat;
            for (auto &node : nodes) {
                for (auto &a : node.args)
                    a = canonical(a);
                if (node.value.kind == 4 || node.value.kind == 5)
                    node.value.output = canonical(node.value.output);
                node.bind();
                flat.push_back(node.value);
            }
            query_core(dlp_qx_rule(created, rule.stratum, rule.predicate, head.size(), head.data(),
                                   initial.size(), initial.data(), flat.data(), flat.size()));
        }
        query_core(dlp_qx_validate(created));
        *out = context.release();
    });
}
