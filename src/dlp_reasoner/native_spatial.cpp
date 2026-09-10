// Immutable resident ECEF point index, C++17, independent of RDF and geodesics.
#include "native_spatial.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <new>
#include <vector>

namespace {
struct Index {
    std::vector<std::array<double, 3>> points;
    std::array<std::vector<std::pair<double, std::size_t>>, 3> axes;
};
using Owner = std::shared_ptr<const Index>;
struct Cursor {
    Owner owner;
    std::array<double, 3> lower, upper;
    std::size_t axis = 0, position = 0, end = 0;
};
} // namespace

extern "C" {
std::uint32_t dlp_spatial_abi() noexcept { return 1; }
int dlp_spatial_new(const double *xyz, std::size_t count, void **output) noexcept {
    if (!output || (count && !xyz) || count > std::numeric_limits<std::size_t>::max() / 3)
        return 1;
    *output = nullptr;
    try {
        auto index = std::make_shared<Index>();
        index->points.reserve(count);
        for (auto &axis : index->axes)
            axis.reserve(count);
        for (std::size_t i = 0; i < count; ++i) {
            std::array<double, 3> point{};
            for (std::size_t j = 0; j < 3; ++j) {
                const auto value = xyz[i * 3 + j];
                if (!std::isfinite(value))
                    return 1;
                point[j] = value;
                index->axes[j].emplace_back(value, i);
            }
            index->points.push_back(point);
        }
        for (auto &axis : index->axes)
            std::sort(axis.begin(), axis.end());
        *output = new Owner(std::move(index));
        return 0;
    } catch (const std::bad_alloc &) {
        return 2;
    } catch (...) {
        return 3;
    }
}
void dlp_spatial_free(void *handle) noexcept { delete static_cast<Owner *>(handle); }
int dlp_spatial_query(void *handle, const double *lower, const double *upper,
                      void **output) noexcept {
    if (!handle || !lower || !upper || !output)
        return 1;
    *output = nullptr;
    try {
        auto cursor = std::make_unique<Cursor>();
        cursor->owner = *static_cast<Owner *>(handle);
        std::size_t best = cursor->owner->points.size() + 1;
        for (std::size_t j = 0; j < 3; ++j) {
            if (!std::isfinite(lower[j]) || !std::isfinite(upper[j]) || lower[j] > upper[j])
                return 1;
            cursor->lower[j] = lower[j];
            cursor->upper[j] = upper[j];
            const auto &axis = cursor->owner->axes[j];
            const auto start = std::lower_bound(
                axis.begin(), axis.end(), lower[j],
                [](const auto &entry, double value) { return entry.first < value; });
            const auto end = std::upper_bound(
                axis.begin(), axis.end(), upper[j],
                [](double value, const auto &entry) { return value < entry.first; });
            const auto size = static_cast<std::size_t>(end - start);
            if (size < best) {
                best = size;
                cursor->axis = j;
                cursor->position = static_cast<std::size_t>(start - axis.begin());
                cursor->end = static_cast<std::size_t>(end - axis.begin());
            }
        }
        *output = cursor.release();
        return 0;
    } catch (const std::bad_alloc &) {
        return 2;
    } catch (...) {
        return 3;
    }
}
int dlp_spatial_next(void *handle, std::uint64_t *rows, std::size_t capacity, std::size_t *count,
                     int *done) noexcept {
    if (!handle || !rows || !capacity || !count || !done)
        return 1;
    auto &cursor = *static_cast<Cursor *>(handle);
    *count = 0;
    while (cursor.position < cursor.end && *count < capacity) {
        const auto id = cursor.owner->axes[cursor.axis][cursor.position++].second;
        const auto &point = cursor.owner->points[id];
        bool inside = true;
        for (std::size_t j = 0; j < 3; ++j)
            inside = inside && point[j] >= cursor.lower[j] && point[j] <= cursor.upper[j];
        if (inside)
            rows[(*count)++] = static_cast<std::uint64_t>(id);
    }
    *done = cursor.position == cursor.end;
    return 0;
}
void dlp_spatial_query_free(void *handle) noexcept { delete static_cast<Cursor *>(handle); }
}
