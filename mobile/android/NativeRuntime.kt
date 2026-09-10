package org.example.dlp

import java.io.Closeable

/** Minimal, serialized wrapper over the native ABI. Call on an application worker.
 * IDs are positive signed 64-bit values in this wrapper; the C ABI uses uint64_t.
 * Loading this class loads a packaged library, never a compiler or downloaded code.
 */
class NativeRuntime(
    eq: Long, neq: Long, top: Long, seed: Long,
    maxRounds: Long = 1_000, maxFacts: Long = 1_000_000,
    maxTerms: Long = 1_000_000, maxDepth: Long = 32,
) : Closeable {
    private var handle: Long = create(eq, neq, top, seed, maxRounds, maxFacts, maxTerms, maxDepth)

    @Synchronized
    override fun close() {
        if (handle != 0L) { destroy(handle); handle = 0L }
    }

    private fun opened(): Long = handle.also { check(it != 0L) { "DLP runtime is closed" } }

    @Synchronized
    fun addTerm(id: Long, orderKey: String, category: Int = 0, literalGroup: Long = 0) {
        require(orderKey.length <= 1_048_576 && !orderKey.contains('\u0000')) { "Order key too large or contains NUL" }
        // JNI modified UTF-8 cannot represent ordinary UTF-8 ordering keys faithfully.
        term(opened(), id, category, orderKey.toByteArray(Charsets.UTF_8), literalGroup)
    }

    @Synchronized
    fun addFact(predicate: Long, arguments: LongArray) = fact(opened(), predicate, arguments)

    /** Convenience inclusion only. Full compiled Horn IR is available in the C ABI. */
    @Synchronized
    fun addUnaryRule(head: Long, body: Long) = unary(opened(), head, body)

    data class Stats(val rounds: Long, val facts: Long, val terms: Long,
                     val violations: Long, val complete: Boolean)

    @Synchronized
    fun materialize(): Stats {
        val values = run(opened())
        return Stats(values[0], values[1], values[2], values[3], values[4] != 0L)
    }

    data class Fact(val predicate: Long, val arguments: List<Long>)

    /** At most 4096 facts/4096 arguments each, with a one-million-cell total cap. */
    @Synchronized
    fun facts(offset: Long = 0, limit: Int = 256, maxArity: Int = 64): List<Fact> {
        require(offset >= 0 && limit in 0..4096 && maxArity in 0..4096)
        return page(opened(), offset, limit, maxArity).map { Fact(it[0], it.drop(1)) }
    }

    private external fun create(eq: Long, neq: Long, top: Long, seed: Long,
                                rounds: Long, facts: Long, terms: Long, depth: Long): Long
    private external fun destroy(pointer: Long)
    private external fun term(pointer: Long, id: Long, category: Int, utf8: ByteArray, group: Long)
    private external fun fact(pointer: Long, predicate: Long, arguments: LongArray)
    private external fun unary(pointer: Long, head: Long, body: Long)
    private external fun run(pointer: Long): LongArray
    private external fun page(pointer: Long, offset: Long, limit: Int, maxArity: Int): Array<LongArray>

    companion object {
        init { System.loadLibrary("dlp_native") }

        /** WGS84 ellipsoid, metres; coordinates are longitude then latitude. */
        @JvmStatic external fun wgs84Distance(longitude1: Double, latitude1: Double,
                                              longitude2: Double, latitude2: Double): Double
    }
}
