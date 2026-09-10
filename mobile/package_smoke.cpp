#include "native_package.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

static void package_check(int status) {
    if (status)
        throw std::runtime_error(dlp_native_package_error());
}
static void query_check(int status) {
    if (status)
        throw std::runtime_error(dlp_qx_last_error());
}
int main(int argc, char **argv) {
    dlp_native_package *package = nullptr;
    dlp_qx_context *query = nullptr;
    try {
        if (argc != 2)
            throw std::runtime_error("Expected smoke .dlpn package path");
        std::ifstream file(argv[1], std::ios::binary | std::ios::ate);
        if (!file || file.tellg() <= 0 || file.tellg() > 65536)
            throw std::runtime_error("Missing or oversized smoke package");
        file.seekg(0);
        std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(file)), {});
        dlp_native_package_options options{{20, 100, 100, 4}, 10000, 10000, 1000};
        package_check(dlp_native_package_load(bytes.data(), bytes.size(), &options, &package));
        size_t terms = 0, predicates = 0, symbols = 0;
        package_check(dlp_native_package_counts(package, &terms, &predicates, &symbols));
        uint64_t answer = 0;
        for (size_t i = 0; i < predicates; ++i) {
            dlp_package_term_view view{};
            package_check(dlp_native_package_predicate(package, i, &view));
            if (std::string(view.lexical, view.lexical_size) == "urn:package-query:answer")
                answer = view.id;
        }
        if (!answer)
            throw std::runtime_error("Missing answer predicate");
        dlp_qx_limits limits{100, 100, 20, 100, 10000};
        package_check(dlp_native_package_prepare_query(package, &limits, nullptr, 0, &query));
        dlp_native_package_free(package);
        package = nullptr; // The query owns the copied materialized data and plan.
        query_check(dlp_qx_run(query, nullptr, nullptr));
        uint64_t output = 0;
        size_t written = 0;
        int done = 0;
        query_check(dlp_qx_result(query, answer, 1, 0, &output, 1, &written, &done));
        if (written != 1 || !done)
            throw std::runtime_error("Expected one package result");
        dlp_domain_value value{};
        query_check(dlp_qx_value(query, output, &value));
        if (value.tag != 2 || value.a != 3)
            throw std::runtime_error("Wrong package result");
        dlp_qx_free(query);
        std::cout << "PASS native package: Horn load, independent query, arithmetic, MIN, filter, "
                     "answer=3\n";
        return 0;
    } catch (const std::exception &error) {
        dlp_qx_free(query);
        dlp_native_package_free(package);
        std::cerr << error.what() << '\n';
        return 1;
    }
}
