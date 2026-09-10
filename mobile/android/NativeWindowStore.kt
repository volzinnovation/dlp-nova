package org.example.dlp

import java.io.Closeable

/** Byte payloads use an application-defined immutable encoding. Call on a worker.
 * Input arrays must not be mutated concurrently with a call. Returned snapshots
 * are independent copies. This wrapper summarizes changes; the C ABI also offers
 * complete addition/retraction streams.
 */
class NativeWindowStore private constructor(private var handle: Long) : Closeable {
    constructor(width: Long, allowedLateness: Long = 0, end: Long = 0, watermark: Long = end,
                maxEvents: Long = 10_000, maxBytes: Long = 16 * 1024 * 1024,
                maxKeys: Long = 1000, context: ByteArray = byteArrayOf()) : this(
        create(width, allowedLateness, end, watermark, maxEvents, maxBytes, maxKeys, context))

    data class Event(val id: ByteArray, val key: ByteArray, val payload: ByteArray,
                     val time: Long, val revision: Long = 0)
    data class Change(val revision: Long, val added: Long, val removed: Long,
                      val historyAdded: Long, val historyRemoved: Long)

    private fun opened(): Long = handle.also { check(it != 0L) { "Native window store is closed" } }
    private fun change(values: LongArray) = Change(values[0], values[1], values[2], values[3], values[4])

    @Synchronized override fun close() {
        if (handle != 0L) { destroy(handle); handle = 0L }
    }

    @Synchronized fun upsert(event: Event): Change = change(put(opened(), event.id, event.key,
        event.payload, event.time, event.revision))

    @Synchronized fun advance(end: Long, watermark: Long = end): Change = change(move(opened(), end, watermark))
    @Synchronized fun checkpoint(): ByteArray = checkpointBytes(opened())

    companion object {
        init { System.loadLibrary("dlp_native") }
        @JvmStatic fun restore(checkpoint: ByteArray, expectedContext: ByteArray? = null,
                               maxCheckpointBytes: Long = 64 * 1024 * 1024,
                               maxEvents: Long = 10_000, maxBytes: Long = 16 * 1024 * 1024,
                               maxKeys: Long = 1000): NativeWindowStore = NativeWindowStore(
            recover(checkpoint, expectedContext, maxCheckpointBytes, maxEvents, maxBytes, maxKeys))
        @JvmStatic private external fun create(width: Long, lateness: Long, end: Long, watermark: Long,
                                                events: Long, bytes: Long, keys: Long, context: ByteArray): Long
        @JvmStatic private external fun destroy(pointer: Long)
        @JvmStatic private external fun put(pointer: Long, id: ByteArray, key: ByteArray, payload: ByteArray,
                                            time: Long, revision: Long): LongArray
        @JvmStatic private external fun move(pointer: Long, end: Long, watermark: Long): LongArray
        @JvmStatic private external fun checkpointBytes(pointer: Long): ByteArray
        @JvmStatic private external fun recover(input: ByteArray, context: ByteArray?, checkpointCap: Long,
                                                eventCap: Long, byteCap: Long, keyCap: Long): Long
    }
}
