package org.example.dlp

import kotlin.math.abs

fun main() {
    val runtime = NativeRuntime(1, 2, 3, 1)
    runtime.use {
        it.addTerm(1, "urn:seed")
        it.addTerm(2, "urn:a:🛣️")
        it.addFact(10, longArrayOf(2))
        it.addUnaryRule(11, 10)
        check(it.materialize().complete)
        check(it.facts().any { row -> row.predicate == 11L && row.arguments == listOf(2L) })
        check(abs(NativeRuntime.wgs84Distance(0.0, 0.0, 1.0, 0.0) - 111319.49079327357) < 1e-6)
        check(runCatching { it.facts(limit = 4097) }.exceptionOrNull() is IllegalArgumentException)
    }
    check(runCatching { runtime.materialize() }.exceptionOrNull() is IllegalStateException)
    runtime.close()
    println("PASS Kotlin/JNI: inference, Unicode term, bounded fact page, WGS84 distance, closed-handle rejection")
    NativeWindowStore(10, allowedLateness = 20, context = "map-v1".toByteArray()).use { window ->
        window.upsert(NativeWindowStore.Event("a".toByteArray(), "car".toByteArray(), byteArrayOf(0), 0))
        window.upsert(NativeWindowStore.Event("b".toByteArray(), "car".toByteArray(), byteArrayOf(1), 5))
        check(window.advance(10).added == 2L)
        NativeWindowStore.restore(window.checkpoint(), "map-v1".toByteArray()).use { restored ->
            val change = restored.advance(100)
            check(change.removed == 2L && change.historyRemoved == 1L)
        }
    }
    println("PASS Kotlin/JNI native windows: events, change counts, checkpoint/resume, idle expiry, predecessor retention")
}
