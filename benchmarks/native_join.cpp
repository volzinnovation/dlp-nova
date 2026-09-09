// Isolated performance experiment; not a production reasoner backend.
// Compute the set projection {(x,z) | left(x,y), right(y,z)} on uint32 IDs.
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <unordered_map>
#include <unordered_set>
#include <vector>

struct JoinResult {
    std::vector<std::uint64_t> rows;
};

extern "C" JoinResult* dlp_join(const std::uint32_t* left, std::size_t left_size,
                                const std::uint32_t* right, std::size_t right_size) noexcept {
    try {
        std::unordered_map<std::uint32_t, std::vector<std::uint32_t>> index;
        for (std::size_t i = 0; i < right_size; ++i)
            index[right[2 * i]].push_back(right[2 * i + 1]);
        std::unordered_set<std::uint64_t> matches;
        for (std::size_t i = 0; i < left_size; ++i) {
            const auto bucket = index.find(left[2 * i + 1]);
            if (bucket == index.end()) continue;
            const auto prefix = std::uint64_t(left[2 * i]) << 32;
            for (const auto z : bucket->second) matches.insert(prefix | z);
        }
        auto result = std::make_unique<JoinResult>();
        result->rows.assign(matches.begin(), matches.end());
        std::sort(result->rows.begin(), result->rows.end());
        return result.release();
    } catch (...) {
        return nullptr;
    }
}

extern "C" std::size_t dlp_join_size(const JoinResult* result) noexcept {
    return result->rows.size();
}

extern "C" const std::uint64_t* dlp_join_data(const JoinResult* result) noexcept {
    return result->rows.data();
}

extern "C" void dlp_join_free(JoinResult* result) noexcept {
    delete result;
}
