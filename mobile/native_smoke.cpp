#include "dlp_native.h"
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>

static void require(bool condition, const char *message) {
    if (!condition)
        throw std::runtime_error(message);
}
int main() {
    try {
        require(dlp_abi_version() == 1 && dlp_domain_abi_version() == 1 &&
                    dlp_runtime_abi_version() == 1 && dlp_spatial_abi() == 1,
                "ABI mismatch");
        dlp_runtime *runtime = nullptr;
        dlp_runtime_limits limits{100, 1000, 1000, 32};
        require(!dlp_runtime_new(1, 2, 3, 1, &limits, &runtime), dlp_runtime_error());
        struct Guard {
            dlp_runtime *p;
            ~Guard() { dlp_runtime_free(p); }
        } guard{runtime};
        require(!dlp_runtime_add_term(runtime, 1, 0, "urn:seed", 0), dlp_runtime_error());
        require(!dlp_runtime_add_term(runtime, 2, 0, "urn:a", 0), dlp_runtime_error());
        uint64_t term = 2;
        require(!dlp_runtime_add_fact(runtime, 10, &term, 1), dlp_runtime_error());
        dlp_runtime_expr variable{1, 0, 0, 0, nullptr};
        dlp_runtime_atom head{11, 1, &variable}, body{10, 1, &variable};
        require(!dlp_runtime_add_rule(runtime, &head, &body, 1, 1, "B(x) :- A(x)"),
                dlp_runtime_error());
        require(!dlp_runtime_materialize(runtime), dlp_runtime_error());
        dlp_runtime_stats stats{};
        require(!dlp_runtime_get_stats(runtime, &stats) && stats.complete,
                "Incomplete materialization");
        bool found = false;
        for (size_t i = 0; i < stats.facts; ++i) {
            uint64_t predicate = 0;
            size_t arity = 0;
            require(!dlp_runtime_fact(runtime, i, &predicate, nullptr, 0, &arity),
                    dlp_runtime_error());
            if (predicate == 11 && arity == 1) {
                require(!dlp_runtime_fact(runtime, i, &predicate, &term, 1, &arity),
                        dlp_runtime_error());
                found = term == 2;
            }
        }
        require(found, "Unary inference missing");
        dlp_domain_value points[2]{};
        points[0].tag = points[1].tag = 9;
        points[1].x = 1;
        dlp_domain_value output{};
        int32_t status = -1;
        require(!dlp_domain_evaluate(41, points, 1, 2, &output, &status) && !status,
                "WGS84 distance failed");
        require(std::abs(output.x - 111319.49079327357) < 1e-6, "WGS84 distance differs");
        dlp_store *store = nullptr;
        require(!dlp_store_new(&store), "Store creation failed");
        dlp_store_free(store);
        const double xyz[3] = {1, 2, 3};
        void *spatial = nullptr;
        require(!dlp_spatial_new(xyz, 1, &spatial), "Spatial index creation failed");
        dlp_spatial_free(spatial);
        std::cout << "PASS native ABI 1; unary inference; WGS84 " << dlp_domain_geodesic_version()
                  << "; relation store; spatial index\n";
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
