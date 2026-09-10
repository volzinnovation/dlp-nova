#include "native_windows.h"
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>

static dlp_window_bytes bytes(const char *value) { return {value, std::strlen(value)}; }
static void check(int result) {
    if (result)
        throw std::runtime_error(dlp_windows_error());
}
int main() {
    dlp_window_store *store = nullptr;
    try {
        dlp_window_config config{10, 20, 0, 0, 100, 10000, 10, 1, 0};
        check(dlp_windows_new(&config, bytes("map-v1"), &store));
        for (auto event : {dlp_window_event{bytes("a"), bytes("car"), bytes("outside"), 0, 0},
                           dlp_window_event{bytes("b"), bytes("car"), bytes("inside"), 5, 0}}) {
            dlp_window_change *change = nullptr;
            check(dlp_windows_upsert(store, &event, {nullptr, 0}, -1, &change));
            dlp_windows_change_free(change);
        }
        dlp_window_change *change = nullptr;
        check(dlp_windows_advance(store, 10, 10, &change));
        dlp_windows_change_free(change);
        dlp_window_event previous{};
        int found = 0;
        check(dlp_windows_predecessor(store, bytes("b"), &previous, &found));
        if (!found || previous.time != 0)
            throw std::runtime_error("Missing predecessor");
        size_t size = 0;
        check(dlp_windows_checkpoint(store, nullptr, 0, &size));
        std::vector<unsigned char> checkpoint(size);
        check(dlp_windows_checkpoint(store, checkpoint.data(), size, &size));
        dlp_windows_free(store);
        store = nullptr;
        auto context = bytes("map-v1");
        check(dlp_windows_restore(checkpoint.data(), checkpoint.size(), 100000, 100, 10000, 10,
                                  &context, &store));
        check(dlp_windows_advance(store, 100, 100, &change));
        dlp_windows_change_free(change);
        dlp_window_rows *rows = nullptr;
        check(dlp_windows_rows(store, 0, &rows));
        size_t count = 0;
        int done = 0;
        check(dlp_windows_next(rows, &previous, 1, &count, &done));
        dlp_windows_rows_free(rows);
        if (count || !done)
            throw std::runtime_error("Idle expiry failed");
        dlp_window_info info{};
        check(dlp_windows_info(store, &info));
        if (info.events != 1)
            throw std::runtime_error("Predecessor retention failed");
        auto rejected = checkpoint;
        rejected.back() ^= 1;
        dlp_window_store *invalid = nullptr;
        if (!dlp_windows_restore(rejected.data(), rejected.size(), 100000, 100, 10000, 10, nullptr,
                                 &invalid) ||
            invalid)
            throw std::runtime_error("Corrupt checkpoint accepted");
        dlp_windows_free(store);
        std::cout << "PASS native windows: active rows, predecessor, checkpoint, idle expiry, "
                     "corruption rejection\n";
        return 0;
    } catch (const std::exception &e) {
        dlp_windows_free(store);
        std::cerr << e.what() << '\n';
        return 1;
    }
}
