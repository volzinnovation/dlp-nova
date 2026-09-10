#include "native_query.h"
#include <iostream>
#include <stdexcept>

static void check(int status) {
    if (status)
        throw std::runtime_error(dlp_qx_last_error());
}
int main() {
    dlp_qx_context *query = nullptr;
    try {
        dlp_qx_limits limits{100, 1000, 10, 100, 10000};
        check(dlp_qx_new(&limits, &query));
        const uint64_t dates[2] = {1, 2};
        check(dlp_qx_rows(query, 10, 2, dates, 1, 1));
        check(dlp_qx_begin(query));
        dlp_domain_value born{}, asof{}, policy{};
        born.tag = asof.tag = 5;
        born.a = 1685;
        born.b = 3;
        born.c = 21;
        asof.a = 1700;
        asof.b = 3;
        asof.c = 22;
        policy.tag = 11;
        policy.a = 1;
        check(dlp_qx_term(query, 1, &born, 0, 1, 0, 0));
        check(dlp_qx_term(query, 2, &asof, 0, 1, 0, 0));
        check(dlp_qx_term(query, 3, &policy, 0, 1, 0, 0));
        check(dlp_qx_term_roles(query, 3, 2));
        const dlp_qx_arg pair[2] = {{0, 0}, {1, 0}};
        const dlp_qx_arg age_args[3] = {{0, 0}, {1, 0}, {-1, 3}};
        const dlp_qx_arg head[1] = {{2, 0}};
        dlp_qx_node body[3]{};
        body[0].kind = 0;
        body[0].predicate = 10;
        body[0].arity = 2;
        body[0].args = pair;
        body[1].kind = 3;
        body[1].opcode = 1;
        body[1].arity = 2;
        body[1].args = pair;
        body[2].kind = 4;
        body[2].opcode = 4;
        body[2].arity = 3;
        body[2].args = age_args;
        body[2].output = {2, 0};
        const uint64_t initial[3] = {0, 0, 0};
        check(dlp_qx_rule(query, 0, 20, 1, head, 3, initial, body, 3));
        check(dlp_qx_run(query, nullptr, nullptr));
        uint64_t answer = 0;
        size_t written = 0;
        int done = 0;
        check(dlp_qx_result(query, 20, 1, 0, &answer, 1, &written, &done));
        if (written != 1 || !done)
            throw std::runtime_error("Expected one completed-years result");
        dlp_domain_value result{};
        check(dlp_qx_value(query, answer, &result));
        if (result.tag != 2 || result.a != 15)
            throw std::runtime_error("Wrong completed-years result");
        dlp_qx_stats stats{};
        check(dlp_qx_get_stats(query, &stats));
        if (stats.domain_evaluations < 2)
            throw std::runtime_error("Domain nodes did not execute natively");
        dlp_qx_free(query);
        std::cout << "PASS native finite query: resident input relation, before filter, "
                     "completedYears bind, age=15\n";
        return 0;
    } catch (const std::exception &e) {
        dlp_qx_free(query);
        std::cerr << e.what() << '\n';
        return 1;
    }
}
