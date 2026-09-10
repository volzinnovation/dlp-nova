#include "native_domains.h"
#include "native_runtime.h"
#include "native_windows.h"
#include <algorithm>
#include <cstdint>
#include <jni.h>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void check(int status) {
    if (status)
        throw std::runtime_error(dlp_runtime_error());
}
void positive(jlong value) {
    if (value <= 0)
        throw std::invalid_argument("IDs and limits must be positive");
}
dlp_runtime *pointer(jlong handle) {
    if (!handle)
        throw std::invalid_argument("DLP runtime is closed");
    return reinterpret_cast<dlp_runtime *>(static_cast<uintptr_t>(handle));
}
void error(JNIEnv *env, const char *type, const char *message) {
    if (!env->ExceptionCheck()) {
        jclass cls = env->FindClass(type);
        if (cls) {
            env->ThrowNew(cls, message);
            env->DeleteLocalRef(cls);
        }
    }
}
template <class Result, class Work>
Result guarded(JNIEnv *env, Result fallback, Work work) noexcept {
    try {
        return work();
    } catch (const std::invalid_argument &e) {
        error(env, "java/lang/IllegalArgumentException", e.what());
    } catch (const std::bad_alloc &) {
        error(env, "java/lang/OutOfMemoryError", "Native DLP allocation failed");
    } catch (const std::exception &e) {
        error(env, "java/lang/IllegalStateException", e.what());
    } catch (...) {
        error(env, "java/lang/IllegalStateException", "Unknown native DLP failure");
    }
    return fallback;
}
jlong integer(uint64_t value) {
    if (value > static_cast<uint64_t>(std::numeric_limits<jlong>::max()))
        throw std::runtime_error("Native value exceeds Kotlin signed 64-bit range");
    return static_cast<jlong>(value);
}
} // namespace

extern "C" JNIEXPORT jlong JNICALL Java_org_example_dlp_NativeRuntime_create(
    JNIEnv *env, jobject, jlong eq, jlong neq, jlong top, jlong seed, jlong rounds, jlong facts,
    jlong terms, jlong depth) {
    return guarded<jlong>(env, 0, [&] {
        for (auto value : {eq, neq, top, seed, rounds, facts, terms, depth})
            positive(value);
        if (dlp_runtime_abi_version() != 1 || dlp_domain_abi_version() != 1)
            throw std::runtime_error("Unsupported DLP native ABI");
        dlp_runtime_limits limits{uint64_t(rounds), uint64_t(facts), uint64_t(terms),
                                  uint64_t(depth)};
        dlp_runtime *result = nullptr;
        check(dlp_runtime_new(eq, neq, top, seed, &limits, &result));
        return static_cast<jlong>(reinterpret_cast<uintptr_t>(result));
    });
}
extern "C" JNIEXPORT void JNICALL Java_org_example_dlp_NativeRuntime_destroy(JNIEnv *env, jobject,
                                                                             jlong handle) {
    guarded<int>(env, 0, [&] {
        dlp_runtime_free(pointer(handle));
        return 0;
    });
}
extern "C" JNIEXPORT void JNICALL Java_org_example_dlp_NativeRuntime_term(
    JNIEnv *env, jobject, jlong handle, jlong id, jint category, jbyteArray utf8, jlong group) {
    guarded<int>(env, 0, [&] {
        positive(id);
        if (!utf8 || category < 0 || category > 2 || group < 0)
            throw std::invalid_argument("Invalid term");
        jsize length = env->GetArrayLength(utf8);
        if (length > 1'048'576)
            throw std::invalid_argument("Term key exceeds 1 MiB");
        std::string key(static_cast<size_t>(length), '\0');
        if (length)
            env->GetByteArrayRegion(utf8, 0, length, reinterpret_cast<jbyte *>(&key[0]));
        if (env->ExceptionCheck())
            return 0;
        if (key.find('\0') != std::string::npos)
            throw std::invalid_argument("Term key contains NUL");
        check(dlp_runtime_add_term(pointer(handle), id, category, key.c_str(), group));
        return 0;
    });
}
extern "C" JNIEXPORT void JNICALL Java_org_example_dlp_NativeRuntime_fact(JNIEnv *env, jobject,
                                                                          jlong handle,
                                                                          jlong predicate,
                                                                          jlongArray values) {
    guarded<int>(env, 0, [&] {
        positive(predicate);
        if (!values)
            throw std::invalid_argument("Null fact arguments");
        jsize size = env->GetArrayLength(values);
        if (size > 4096)
            throw std::invalid_argument("Fact arity exceeds 4096");
        std::vector<jlong> raw(size);
        if (size)
            env->GetLongArrayRegion(values, 0, size, raw.data());
        if (env->ExceptionCheck())
            return 0;
        std::vector<uint64_t> arguments;
        arguments.reserve(size);
        for (auto value : raw) {
            positive(value);
            arguments.push_back(value);
        }
        check(dlp_runtime_add_fact(pointer(handle), predicate, arguments.data(), arguments.size()));
        return 0;
    });
}
extern "C" JNIEXPORT void JNICALL Java_org_example_dlp_NativeRuntime_unary(JNIEnv *env, jobject,
                                                                           jlong handle, jlong head,
                                                                           jlong body) {
    guarded<int>(env, 0, [&] {
        positive(head);
        positive(body);
        dlp_runtime_expr expression{1, 0, 0, 0, nullptr};
        dlp_runtime_atom conclusion{uint64_t(head), 1, &expression},
            premise{uint64_t(body), 1, &expression};
        check(dlp_runtime_add_rule(pointer(handle), &conclusion, &premise, 1, 1,
                                   "Kotlin unary inclusion"));
        return 0;
    });
}
extern "C" JNIEXPORT jlongArray JNICALL Java_org_example_dlp_NativeRuntime_run(JNIEnv *env, jobject,
                                                                               jlong handle) {
    return guarded<jlongArray>(env, nullptr, [&] {
        auto *runtime = pointer(handle);
        check(dlp_runtime_materialize(runtime));
        dlp_runtime_stats stats{};
        check(dlp_runtime_get_stats(runtime, &stats));
        jlong values[] = {integer(stats.rounds), integer(stats.facts), integer(stats.terms),
                          integer(stats.violations), stats.complete};
        auto result = env->NewLongArray(5);
        if (result)
            env->SetLongArrayRegion(result, 0, 5, values);
        return result;
    });
}
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_example_dlp_NativeRuntime_page(
    JNIEnv *env, jobject, jlong handle, jlong offset, jint limit, jint max_arity) {
    return guarded<jobjectArray>(env, nullptr, [&] {
        if (offset < 0 || limit < 0 || limit > 4096 || max_arity < 0 || max_arity > 4096)
            throw std::invalid_argument("Invalid fact page limits");
        auto *runtime = pointer(handle);
        dlp_runtime_stats stats{};
        check(dlp_runtime_get_stats(runtime, &stats));
        if (!stats.complete)
            throw std::runtime_error("Runtime has no complete result");
        if (uint64_t(offset) > stats.facts)
            throw std::invalid_argument("Fact offset out of range");
        auto count = static_cast<jsize>(std::min(uint64_t(limit), stats.facts - uint64_t(offset)));
        jclass row_class = env->FindClass("[J");
        if (!row_class)
            return static_cast<jobjectArray>(nullptr);
        auto result = env->NewObjectArray(count, row_class, nullptr);
        env->DeleteLocalRef(row_class);
        if (!result)
            return result;
        size_t cells = 0;
        for (jsize i = 0; i < count; ++i) {
            uint64_t predicate = 0;
            size_t arity = 0;
            check(dlp_runtime_fact(runtime, uint64_t(offset) + i, &predicate, nullptr, 0, &arity));
            if (arity > size_t(max_arity))
                throw std::invalid_argument("Fact exceeds maxArity");
            cells += arity + 1;
            if (cells > 1'000'000)
                throw std::invalid_argument("Fact page exceeds argument budget");
            std::vector<uint64_t> arguments(arity);
            check(dlp_runtime_fact(runtime, uint64_t(offset) + i, &predicate, arguments.data(),
                                   arity, &arity));
            std::vector<jlong> values;
            values.reserve(arity + 1);
            values.push_back(integer(predicate));
            for (auto value : arguments)
                values.push_back(integer(value));
            auto row = env->NewLongArray(static_cast<jsize>(values.size()));
            if (!row)
                return static_cast<jobjectArray>(nullptr);
            env->SetLongArrayRegion(row, 0, static_cast<jsize>(values.size()), values.data());
            env->SetObjectArrayElement(result, i, row);
            env->DeleteLocalRef(row);
            if (env->ExceptionCheck())
                return static_cast<jobjectArray>(nullptr);
        }
        return result;
    });
}
extern "C" JNIEXPORT jdouble JNICALL Java_org_example_dlp_NativeRuntime_wgs84Distance(
    JNIEnv *env, jclass, jdouble longitude1, jdouble latitude1, jdouble longitude2,
    jdouble latitude2) {
    return guarded<jdouble>(env, 0, [&] {
        dlp_domain_value points[2]{}, output{};
        points[0].tag = points[1].tag = 9;
        points[0].x = longitude1;
        points[0].y = latitude1;
        points[1].x = longitude2;
        points[1].y = latitude2;
        int32_t status = -1;
        if (dlp_domain_evaluate(41, points, 1, 2, &output, &status) || status)
            throw std::invalid_argument("Invalid or unavailable WGS84 distance");
        return output.x;
    });
}

namespace {
void window_check(int result) {
    if (result)
        throw std::runtime_error(dlp_windows_error());
}
dlp_window_store *window_pointer(jlong value) {
    if (!value)
        throw std::invalid_argument("Native window store is closed");
    return reinterpret_cast<dlp_window_store *>(static_cast<uintptr_t>(value));
}
std::string array(JNIEnv *env, jbyteArray input, uint64_t cap) {
    if (!input)
        throw std::invalid_argument("Null byte array");
    jsize length = env->GetArrayLength(input);
    if (uint64_t(length) > cap)
        throw std::invalid_argument("Byte array exceeds configured cap");
    std::string result(length, '\0');
    if (length)
        env->GetByteArrayRegion(input, 0, length, reinterpret_cast<jbyte *>(&result[0]));
    if (env->ExceptionCheck())
        throw std::runtime_error("Cannot copy input bytes");
    return result;
}
dlp_window_bytes window_bytes(const std::string &value) { return {value.data(), value.size()}; }
jlongArray window_change(JNIEnv *env, dlp_window_change *publication) {
    struct Guard {
        dlp_window_change *p;
        ~Guard() { dlp_windows_change_free(p); }
    } guard{publication};
    uint64_t revision = 0;
    window_check(dlp_windows_change_revision(publication, &revision));
    jlong values[5] = {integer(revision), 0, 0, 0, 0};
    dlp_window_event buffer[128];
    for (uint32_t mode = 0; mode < 4; ++mode) {
        size_t count = 0;
        int done = 0;
        while (!done) {
            window_check(dlp_windows_change_next(publication, mode, buffer, 128, &count, &done));
            values[mode + 1] += static_cast<jlong>(count);
        }
    }
    auto result = env->NewLongArray(5);
    if (result)
        env->SetLongArrayRegion(result, 0, 5, values);
    return result;
}
} // namespace
extern "C" JNIEXPORT jlong JNICALL Java_org_example_dlp_NativeWindowStore_create(
    JNIEnv *env, jclass, jlong width, jlong lateness, jlong end, jlong watermark, jlong events,
    jlong bytes, jlong keys, jbyteArray context) {
    return guarded<jlong>(env, 0, [&] {
        positive(width);
        positive(events);
        positive(bytes);
        positive(keys);
        auto text = array(env, context, uint64_t(bytes));
        dlp_window_config cfg{width,           lateness,       end, watermark, uint64_t(events),
                              uint64_t(bytes), uint64_t(keys), 1,   0};
        dlp_window_store *result = nullptr;
        window_check(dlp_windows_new(&cfg, window_bytes(text), &result));
        return static_cast<jlong>(reinterpret_cast<uintptr_t>(result));
    });
}
extern "C" JNIEXPORT void JNICALL Java_org_example_dlp_NativeWindowStore_destroy(JNIEnv *env,
                                                                                 jclass,
                                                                                 jlong handle) {
    guarded<int>(env, 0, [&] {
        dlp_windows_free(window_pointer(handle));
        return 0;
    });
}
extern "C" JNIEXPORT jlongArray JNICALL Java_org_example_dlp_NativeWindowStore_put(
    JNIEnv *env, jclass, jlong handle, jbyteArray id, jbyteArray key, jbyteArray payload,
    jlong time, jlong revision) {
    return guarded<jlongArray>(env, nullptr, [&] {
        auto *store = window_pointer(handle);
        dlp_window_config cfg{};
        dlp_window_bytes context{};
        window_check(dlp_windows_config(store, &cfg, &context));
        auto identity = array(env, id, cfg.max_bytes), grouping = array(env, key, cfg.max_bytes),
             row = array(env, payload, cfg.max_bytes);
        dlp_window_event event{window_bytes(identity), window_bytes(grouping), window_bytes(row),
                               time, revision};
        dlp_window_change *publication = nullptr;
        window_check(dlp_windows_upsert(store, &event, {nullptr, 0}, -1, &publication));
        return window_change(env, publication);
    });
}
extern "C" JNIEXPORT jlongArray JNICALL Java_org_example_dlp_NativeWindowStore_move(
    JNIEnv *env, jclass, jlong handle, jlong end, jlong watermark) {
    return guarded<jlongArray>(env, nullptr, [&] {
        dlp_window_change *publication = nullptr;
        window_check(dlp_windows_advance(window_pointer(handle), end, watermark, &publication));
        return window_change(env, publication);
    });
}
extern "C" JNIEXPORT jbyteArray JNICALL
Java_org_example_dlp_NativeWindowStore_checkpointBytes(JNIEnv *env, jclass, jlong handle) {
    return guarded<jbyteArray>(env, nullptr, [&] {
        auto *store = window_pointer(handle);
        size_t size = 0;
        window_check(dlp_windows_checkpoint(store, nullptr, 0, &size));
        if (size > uint64_t(std::numeric_limits<jsize>::max()))
            throw std::invalid_argument("Checkpoint exceeds JVM array size");
        std::vector<char> output(size);
        window_check(dlp_windows_checkpoint(store, output.data(), size, &size));
        auto result = env->NewByteArray(static_cast<jsize>(size));
        if (result)
            env->SetByteArrayRegion(result, 0, static_cast<jsize>(size),
                                    reinterpret_cast<const jbyte *>(output.data()));
        return result;
    });
}
extern "C" JNIEXPORT jlong JNICALL Java_org_example_dlp_NativeWindowStore_recover(
    JNIEnv *env, jclass, jbyteArray input, jbyteArray context, jlong checkpoint_cap,
    jlong event_cap, jlong byte_cap, jlong key_cap) {
    return guarded<jlong>(env, 0, [&] {
        for (auto value : {checkpoint_cap, event_cap, byte_cap, key_cap})
            positive(value);
        auto data = array(env, input, uint64_t(checkpoint_cap));
        auto text = context ? array(env, context, uint64_t(byte_cap)) : std::string();
        auto expected = window_bytes(text);
        dlp_window_store *result = nullptr;
        window_check(dlp_windows_restore(data.data(), data.size(), checkpoint_cap, event_cap,
                                         byte_cap, key_cap, context ? &expected : nullptr,
                                         &result));
        return static_cast<jlong>(reinterpret_cast<uintptr_t>(result));
    });
}
